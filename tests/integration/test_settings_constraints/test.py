import pytest

from helpers.cluster import ClickHouseCluster

cluster = ClickHouseCluster(__file__)
instance = cluster.add_instance("instance", user_configs=["configs/users.xml"])


@pytest.fixture(scope="module")
def started_cluster():
    try:
        cluster.start()
        yield cluster

    finally:
        cluster.shutdown()


def test_system_settings(started_cluster):
    assert (
        instance.query(
            "SELECT name, value, min, max, readonly from system.settings WHERE name = 'force_index_by_date'"
        )
        == "force_index_by_date\t0\t\\N\t\\N\t1\n"
    )

    assert (
        instance.query(
            "SELECT name, value, min, max, readonly from system.settings WHERE name = 'max_memory_usage'"
        )
        == "max_memory_usage\t10000000000\t5000000000\t20000000000\t0\n"
    )

    assert (
        instance.query(
            "SELECT name, value, min, max, readonly from system.settings WHERE name = 'readonly'"
        )
        == "readonly\t0\t\\N\t\\N\t0\n"
    )

    assert (
        instance.query(
            "SELECT name, value, min, max, readonly from system.settings WHERE name = 'alter_sync'"
        )
        == "alter_sync\t2\t\\N\t\\N\t1\n"
    )


def test_system_constraints(started_cluster):
    assert_query_settings(
        instance,
        "SELECT 1",
        settings={"readonly": 0},
        exception="Cannot modify 'readonly'",
        user="readonly_user",
    )

    assert_query_settings(
        instance,
        "SELECT 1",
        settings={"allow_ddl": 1},
        exception="Cannot modify 'allow_ddl'",
        user="no_dll_user",
    )


def test_read_only_constraint(started_cluster):
    # Default value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='force_index_by_date'",
        settings={},
        result="0",
    )

    # Invalid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='force_index_by_date'",
        settings={"force_index_by_date": 1},
        result=None,
        exception="Setting force_index_by_date should not be changed",
    )

    # Invalid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name= 'replication_alter_partitions_sync'",
        settings={"replication_alter_partitions_sync": 1},
        result=None,
        exception="Setting alter_sync should not be changed",
    )

    # Invalid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name= 'alter_sync'",
        settings={"alter_sync": 1},
        result=None,
        exception="Setting alter_sync should not be changed",
    )


def test_min_constraint(started_cluster):
    # Default value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        {},
        result="10000000000",
    )

    # Valid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 5000000000},
        result="5000000000",
    )

    # Invalid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 4999999999},
        result=None,
        exception="Setting max_memory_usage shouldn't be less than 5000000000",
    )


def test_max_constraint(started_cluster):
    # Default value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        {},
        result="10000000000",
    )

    # Valid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 20000000000},
        result="20000000000",
    )

    # Invalid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 20000000001},
        result=None,
        exception="Setting max_memory_usage shouldn't be greater than 20000000000",
    )


def test_disallowed_constraint(started_cluster):
    # Default value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        {},
        result="10000000000",
    )

    # Valid value
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 6000000002},
        result="6000000002",
    )

    # Invalid values
    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 6000000000},
        result=None,
        exception=" Setting max_memory_usage shouldn't be 6000000000",
    )

    assert_query_settings(
        instance,
        "SELECT value FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 6000000001},
        result=None,
        exception=" Setting max_memory_usage shouldn't be 6000000001",
    )

    # Check that the disallowed values returned are as expected
    assert_query_settings(
        instance,
        "SELECT disallowed_values FROM system.settings WHERE name='max_memory_usage'",
        settings={"max_memory_usage": 10000000000},
        result="['6000000000','6000000001']"
    )


def test_disallowed_constraint_merge_tree(started_cluster):
    # Default value
    assert_query_settings(
        instance,
        "SELECT value FROM system.merge_tree_settings WHERE name='max_parts_in_total'",
        {},
        result="100000",
    )

    assert_query_settings(
        instance,
        "SELECT disallowed_values FROM system.merge_tree_settings WHERE name='max_parts_in_total'",
        {},
        result="['5000']",
    )

    # Test by creating a merge tree table with valid setting, followed by alters with both valid and invalid (disallowed) settings
    # Valid values
    instance.query("CREATE TABLE test (x Int) ENGINE=MergeTree ORDER BY x SETTINGS max_parts_in_total=2000")
    instance.query("ALTER TABLE test MODIFY SETTING max_parts_in_total=3000")
    # Invalid value
    assert " Setting max_parts_in_total shouldn't be 5000." in instance.query_and_get_error(
        "ALTER TABLE test MODIFY SETTING max_parts_in_total=5000")
    # Clean up
    instance.query("DROP TABLE IF EXISTS test")


def assert_query_settings(
    instance, query, settings, result=None, exception=None, user=None
):
    """
    Try and send the query with custom settings via all available methods:
    1. TCP Protocol with settings packet
    2. HTTP Protocol with settings params
    3. TCP Protocol with session level settings
    4. TCP Protocol with query level settings
    """

    if not settings:
        settings = {}

    # tcp level settings
    if exception:
        assert exception in instance.query_and_get_error(
            query, settings=settings, user=user
        )
    else:
        assert instance.query(query, settings=settings, user=user).strip() == result

    # http level settings
    if exception:
        assert exception in instance.http_query_and_get_error(
            query, params=settings, user=user
        )
    else:
        assert instance.http_query(query, params=settings, user=user).strip() == result

    # session level settings
    queries = ""

    for k, v in list(settings.items()):
        queries += "SET {}={};\n".format(k, v)

    queries += query

    if exception:
        assert exception in instance.query_and_get_error(queries, user=user)
    else:
        assert instance.query(queries, user=user).strip() == result

    if settings:
        query += " SETTINGS "
        for ix, (k, v) in enumerate(settings.items()):
            query += "{} = {}".format(k, v)
            if ix != len(settings) - 1:
                query += ", "

    if exception:
        assert exception in instance.query_and_get_error(queries, user=user)
    else:
        assert instance.query(queries, user=user).strip() == result
