#pragma once

#include <Storages/MergeTree/MergeTreeData.h>
#include <Storages/MergeTree/MergeProgress.h>
#include <Storages/MergeTree/FutureMergedMutatedPart.h>
#include <Storages/MergeTree/IMergedBlockOutputStream.h>
#include <Storages/MergeTree/PartitionActionBlocker.h>
#include <Storages/MutationCommands.h>


namespace DB
{


class MutateTask;
using MutateTaskPtr = std::shared_ptr<MutateTask>;


class MergeTreeDataMergerMutator;

struct MutationContext;

class MutateTask
{
public:
    static constexpr auto TEMP_DIRECTORY_PREFIX = "tmp_mut_";

    MutateTask(
        FutureMergedMutatedPartPtr future_part_,
        StorageMetadataPtr metadata_snapshot_,
        MutationCommandsConstPtr commands_,
        MergeListEntry * mutate_entry_,
        time_t time_of_mutation_,
        ContextPtr context_,
        ReservationSharedPtr space_reservation_,
        TableLockHolder & table_lock_holder_,
        const MergeTreeTransactionPtr & txn,
        MergeTreeData & data_,
        MergeTreeDataMergerMutator & mutator_,
        PartitionActionBlocker & merges_blocker_,
        bool need_prefix_);

    bool execute();
    void cancel() noexcept;

    void updateProfileEvents() const;

    std::future<MergeTreeData::MutableDataPartPtr> getFuture()
    {
        return promise.get_future();
    }

    const HardlinkedFiles & getHardlinkedFiles() const;

private:

    bool prepare();

    enum class State : uint8_t
    {
        NEED_PREPARE,
        NEED_EXECUTE
    };

    State state{State::NEED_PREPARE};

    std::promise<MergeTreeData::MutableDataPartPtr> promise;

    std::shared_ptr<MutationContext> ctx;
    ExecutableTaskPtr task;

};

[[ maybe_unused]] static MergeTreeData::MutableDataPartPtr executeHere(MutateTaskPtr task)
{
    while (task->execute()) {}
    return task->getFuture().get();
}

}
