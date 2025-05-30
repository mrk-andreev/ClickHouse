#include <Interpreters/InterpreterDeleteQuery.h>
#include <Interpreters/InterpreterFactory.h>

#include <Access/ContextAccess.h>
#include <Core/Settings.h>
#include <Core/ServerSettings.h>
#include <Databases/DatabaseReplicated.h>
#include <Databases/IDatabase.h>
#include <Interpreters/Context.h>
#include <Interpreters/DatabaseCatalog.h>
#include <Interpreters/FunctionNameNormalizer.h>
#include <Interpreters/InterpreterAlterQuery.h>
#include <Interpreters/MutationsInterpreter.h>
#include <Parsers/parseQuery.h>
#include <Parsers/ParserAlterQuery.h>
#include <Parsers/ASTDeleteQuery.h>
#include <Parsers/ASTLiteral.h>
#include <Parsers/CommonParsers.h>
#include <Parsers/ParserDropQuery.h>
#include <Storages/AlterCommands.h>
#include <Storages/IStorage.h>
#include <Storages/MutationCommands.h>
#include <Storages/MergeTree/MergeTreeSettings.h>


namespace DB
{
namespace Setting
{
    extern const SettingsBool enable_lightweight_delete;
    extern const SettingsUInt64 lightweight_deletes_sync;
    extern const SettingsSeconds lock_acquire_timeout;
}

namespace MergeTreeSetting
{
    extern const MergeTreeSettingsLightweightMutationProjectionMode lightweight_mutation_projection_mode;
}

namespace ServerSetting
{
    extern const ServerSettingsBool disable_insertion_and_mutation;
}

namespace ErrorCodes
{
    extern const int TABLE_IS_READ_ONLY;
    extern const int SUPPORT_IS_DISABLED;
    extern const int BAD_ARGUMENTS;
    extern const int QUERY_IS_PROHIBITED;
}


InterpreterDeleteQuery::InterpreterDeleteQuery(const ASTPtr & query_ptr_, ContextPtr context_) : WithContext(context_), query_ptr(query_ptr_)
{
}


BlockIO InterpreterDeleteQuery::execute()
{
    FunctionNameNormalizer::visit(query_ptr.get());
    const ASTDeleteQuery & delete_query = query_ptr->as<ASTDeleteQuery &>();
    auto table_id = getContext()->resolveStorageID(delete_query, Context::ResolveOrdinary);

    getContext()->checkAccess(AccessType::ALTER_DELETE, table_id);

    query_ptr->as<ASTDeleteQuery &>().setDatabase(table_id.database_name);

    /// First check table storage for validations.
    StoragePtr table = DatabaseCatalog::instance().getTable(table_id, getContext());
    checkStorageSupportsTransactionsIfNeeded(table, getContext());
    if (table->isStaticStorage())
        throw Exception(ErrorCodes::TABLE_IS_READ_ONLY, "Table is read-only");

    if (getContext()->getGlobalContext()->getServerSettings()[ServerSetting::disable_insertion_and_mutation])
        throw Exception(ErrorCodes::QUERY_IS_PROHIBITED, "Delete queries are prohibited");

    DatabasePtr database = DatabaseCatalog::instance().getDatabase(table_id.database_name);
    if (database->shouldReplicateQuery(getContext(), query_ptr))
    {
        auto guard = DatabaseCatalog::instance().getDDLGuard(table_id.database_name, table_id.table_name);
        guard->releaseTableLock();
        return database->tryEnqueueReplicatedDDL(query_ptr, getContext(), {});
    }

    /// DELETE FROM ... WHERE 1 should be executed as truncate
    if ((table->supportsDelete() || table->supportsLightweightDelete()) && isAlwaysTruePredicate(delete_query.predicate))
    {
        auto context = getContext();
        context->checkAccess(AccessType::TRUNCATE, table_id);
        table->checkTableCanBeDropped(context);

        TableExclusiveLockHolder table_excl_lock;
        /// We don't need any lock for ReplicatedMergeTree and for simple MergeTree
        /// For the rest of tables types exclusive lock is needed
        if (!std::dynamic_pointer_cast<MergeTreeData>(table))
            table_excl_lock = table->lockExclusively(context->getCurrentQueryId(), context->getSettingsRef()[Setting::lock_acquire_timeout]);

        String truncate_query = "TRUNCATE TABLE " + table->getStorageID().getFullTableName()
            + (delete_query.cluster.empty() ? "" : " ON CLUSTER " + backQuoteIfNeed(delete_query.cluster));

        ParserDropQuery parser;
        auto current_query_ptr = parseQuery(
            parser,
            truncate_query.data(),
            truncate_query.data() + truncate_query.size(),
            "ALTER query",
            0,
            DBMS_DEFAULT_MAX_PARSER_DEPTH,
            DBMS_DEFAULT_MAX_PARSER_BACKTRACKS);

        auto metadata_snapshot = table->getInMemoryMetadataPtr();
        /// Drop table data, don't touch metadata
        table->truncate(current_query_ptr, metadata_snapshot, context, table_excl_lock);
        return {};
    }

    auto table_lock = table->lockForShare(getContext()->getCurrentQueryId(), getContext()->getSettingsRef()[Setting::lock_acquire_timeout]);
    auto metadata_snapshot = table->getInMemoryMetadataPtr();

    if (table->supportsDelete())
    {
        /// Convert to MutationCommand
        MutationCommands mutation_commands;
        MutationCommand mut_command;

        mut_command.type = MutationCommand::Type::DELETE;
        mut_command.predicate = delete_query.predicate;

        mutation_commands.emplace_back(mut_command);

        table->checkMutationIsPossible(mutation_commands, getContext()->getSettingsRef());
        MutationsInterpreter::Settings settings(false);
        MutationsInterpreter(table, metadata_snapshot, mutation_commands, getContext(), settings).validate();
        table->mutate(mutation_commands, getContext());
        return {};
    }
    if (table->supportsLightweightDelete())
    {
        if (!getContext()->getSettingsRef()[Setting::enable_lightweight_delete])
            throw Exception(ErrorCodes::SUPPORT_IS_DISABLED,
                            "Lightweight delete mutate is disabled. "
                            "Set `enable_lightweight_delete` setting to enable it");

        if (metadata_snapshot->hasProjections())
        {
            if (const auto * merge_tree_data = dynamic_cast<const MergeTreeData *>(table.get()))
                if ((*merge_tree_data->getSettings())[MergeTreeSetting::lightweight_mutation_projection_mode] == LightweightMutationProjectionMode::THROW)
                    throw Exception(ErrorCodes::SUPPORT_IS_DISABLED,
                        "DELETE query is not allowed for table {} because as it has projections and setting "
                        "lightweight_mutation_projection_mode is set to THROW. "
                        "User should change lightweight_mutation_projection_mode OR "
                        "drop all the projections manually before running the query",
                        table_id.getFullTableName());
        }

        /// Build "ALTER ... UPDATE _row_exists = 0 WHERE predicate" query
        String alter_query = "ALTER TABLE " + table->getStorageID().getFullTableName()
            + (delete_query.cluster.empty() ? "" : " ON CLUSTER " + backQuoteIfNeed(delete_query.cluster)) + " UPDATE `_row_exists` = 0"
            + (delete_query.partition ? " IN PARTITION " + delete_query.partition->formatWithSecretsOneLine() : "") + " WHERE "
            + delete_query.predicate->formatWithSecretsOneLine();

        ParserAlterQuery parser;
        ASTPtr alter_ast = parseQuery(
            parser,
            alter_query.data(),
            alter_query.data() + alter_query.size(),
            "ALTER query",
            0,
            DBMS_DEFAULT_MAX_PARSER_DEPTH,
            DBMS_DEFAULT_MAX_PARSER_BACKTRACKS);

        auto context = Context::createCopy(getContext());
        context->setSetting("mutations_sync", Field(context->getSettingsRef()[Setting::lightweight_deletes_sync]));
        InterpreterAlterQuery alter_interpreter(alter_ast, context);
        return alter_interpreter.execute();
    }

    throw Exception(ErrorCodes::BAD_ARGUMENTS, "DELETE query is not supported for table {}", table->getStorageID().getFullTableName());
}

void registerInterpreterDeleteQuery(InterpreterFactory & factory)
{
    auto create_fn = [] (const InterpreterFactory::Arguments & args)
    {
        return std::make_unique<InterpreterDeleteQuery>(args.query, args.context);
    };
    factory.registerInterpreter("InterpreterDeleteQuery", create_fn);
}

}
