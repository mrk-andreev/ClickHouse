from helpers.kafka.common_direct import *
import helpers.kafka.common as k

cluster = ClickHouseCluster(__file__)
instance = cluster.add_instance(
    "instance",
    main_configs=["configs/kafka.xml"],
    with_kafka=True,
)


@pytest.fixture(scope="module")
def kafka_cluster():
    try:
        cluster.start()
        kafka_id = instance.cluster.kafka_docker_id
        print(("kafka_id is {}".format(kafka_id)))
        yield cluster
    finally:
        cluster.shutdown()


def test_bad_messages_parsing_stream(kafka_cluster):
    admin_client = KafkaAdminClient(
        bootstrap_servers="localhost:{}".format(kafka_cluster.kafka_port)
    )

    for format_name in [
        "TSV",
        "TSKV",
        "CSV",
        "Values",
        "JSON",
        "JSONEachRow",
        "JSONCompactEachRow",
        "JSONObjectEachRow",
        "Avro",
        "RowBinary",
        "JSONColumns",
        "JSONColumnsWithMetadata",
        "Native",
        "Arrow",
        "ArrowStream",
        "Parquet",
        "ORC",
        "JSONCompactColumns",
        "BSONEachRow",
        "MySQLDump",
    ]:
        print(format_name)

        k.kafka_create_topic(admin_client, f"{format_name}_err")

        instance.query(
            f"""
            DROP TABLE IF EXISTS view;
            DROP TABLE IF EXISTS kafka;

            CREATE TABLE kafka (key UInt64, value UInt64)
                ENGINE = Kafka
                SETTINGS kafka_broker_list = 'kafka1:19092',
                         kafka_topic_list = '{format_name}_err',
                         kafka_group_name = '{format_name}',
                         kafka_format = '{format_name}',
                         kafka_flush_interval_ms=1000,
                         kafka_handle_error_mode='stream';

            CREATE MATERIALIZED VIEW view Engine=Log AS
                SELECT _error FROM kafka WHERE length(_error) != 0 ;
        """
        )

        messages = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
        k.kafka_produce(kafka_cluster, f"{format_name}_err", messages)

        attempt = 0
        rows = 0
        while attempt < 500:
            rows = int(instance.query("SELECT count() FROM view"))
            if rows == len(messages):
                break
            attempt += 1

        assert rows == len(messages)

        k.kafka_delete_topic(admin_client, f"{format_name}_err")

    protobuf_schema = """
syntax = "proto3";

message Message {
  uint64 key = 1;
  uint64 value = 2;
};
"""

    instance.create_format_schema("schema_test_errors.proto", protobuf_schema)

    for format_name in ["Protobuf", "ProtobufSingle", "ProtobufList"]:
        instance.query(
            f"""
            DROP TABLE IF EXISTS view;
            DROP TABLE IF EXISTS kafka;

            CREATE TABLE kafka (key UInt64, value UInt64)
                ENGINE = Kafka
                SETTINGS kafka_broker_list = 'kafka1:19092',
                         kafka_topic_list = '{format_name}_err',
                         kafka_group_name = '{format_name}',
                         kafka_format = '{format_name}',
                         kafka_handle_error_mode='stream',
                         kafka_flush_interval_ms=1000,
                         kafka_schema='schema_test_errors:Message';

            CREATE MATERIALIZED VIEW view Engine=Log AS
                SELECT _error FROM kafka WHERE length(_error) != 0 ;
        """
        )

        print(format_name)

        k.kafka_create_topic(admin_client, f"{format_name}_err")

        messages = ["qwertyuiop", "poiuytrewq", "zxcvbnm"]
        k.kafka_produce(kafka_cluster, f"{format_name}_err", messages)

        attempt = 0
        rows = 0
        while attempt < 500:
            rows = int(instance.query("SELECT count() FROM view"))
            if rows == len(messages):
                break
            attempt += 1

        assert rows == len(messages)

        k.kafka_delete_topic(admin_client, f"{format_name}_err")

    capn_proto_schema = """
@0xd9dd7b35452d1c4f;

struct Message
{
    key @0 : UInt64;
    value @1 : UInt64;
}
"""

    instance.create_format_schema("schema_test_errors.capnp", capn_proto_schema)
    instance.query(
        f"""
            DROP TABLE IF EXISTS view;
            DROP TABLE IF EXISTS kafka;

            CREATE TABLE kafka (key UInt64, value UInt64)
                ENGINE = Kafka
                SETTINGS kafka_broker_list = 'kafka1:19092',
                         kafka_topic_list = 'CapnProto_err',
                         kafka_group_name = 'CapnProto',
                         kafka_format = 'CapnProto',
                         kafka_handle_error_mode='stream',
                         kafka_flush_interval_ms=1000,
                         kafka_schema='schema_test_errors:Message';

            CREATE MATERIALIZED VIEW view Engine=Log AS
                SELECT _error FROM kafka WHERE length(_error) != 0;
        """
    )

    print("CapnProto")

    k.kafka_create_topic(admin_client, "CapnProto_err")

    messages = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
    k.kafka_produce(kafka_cluster, "CapnProto_err", messages)

    attempt = 0
    rows = 0
    while attempt < 500:
        rows = int(instance.query("SELECT count() FROM view"))
        if rows == len(messages):
            break
        attempt += 1

    assert rows == len(messages)

    k.kafka_delete_topic(admin_client, "CapnProto_err")


def test_bad_messages_parsing_exception(kafka_cluster, max_retries=20):
    admin_client = KafkaAdminClient(
        bootstrap_servers="localhost:{}".format(kafka_cluster.kafka_port)
    )

    for format_name in [
        "Avro",
        "JSONEachRow",
    ]:
        print(format_name)

        k.kafka_create_topic(admin_client, f"{format_name}_parsing_err")

        instance.query(
            f"""
            DROP TABLE IF EXISTS view_{format_name};
            DROP TABLE IF EXISTS kafka_{format_name};
            DROP TABLE IF EXISTS kafka;

            CREATE TABLE kafka_{format_name} (key UInt64, value UInt64)
                ENGINE = Kafka
                SETTINGS kafka_broker_list = 'kafka1:19092',
                         kafka_topic_list = '{format_name}_parsing_err',
                         kafka_group_name = '{format_name}',
                         kafka_format = '{format_name}',
                         kafka_flush_interval_ms=1000,
                         kafka_num_consumers = 1;

            CREATE MATERIALIZED VIEW view_{format_name} Engine=Log AS
                SELECT * FROM kafka_{format_name};
        """
        )

        k.kafka_produce(
            kafka_cluster,
            f"{format_name}_parsing_err",
            ["qwertyuiop", "asdfghjkl", "zxcvbnm"],
        )

    expected_result = """avro::Exception: Invalid data file. Magic does not match: : while parsing Kafka message (topic: Avro_parsing_err, partition: 0, offset: 0)\\'|1|1|1|default|kafka_Avro
Cannot parse input: expected \\'{\\' before: \\'qwertyuiop\\': (at row 1)\\n: while parsing Kafka message (topic: JSONEachRow_parsing_err, partition:|1|1|1|default|kafka_JSONEachRow
"""
    # filter out stacktrace in exceptions.text[1] because it is hardly stable enough
    result_system_kafka_consumers = instance.query_with_retry(
        """
        SELECT substr(exceptions.text[1], 1, 139), length(exceptions.text) > 1 AND length(exceptions.text) < 15, length(exceptions.time) > 1 AND length(exceptions.time) < 15, abs(dateDiff('second', exceptions.time[1], now())) < 40, database, table FROM system.kafka_consumers WHERE table in('kafka_Avro', 'kafka_JSONEachRow') ORDER BY table, assignments.partition_id[1]
        """,
        retry_count=max_retries,
        sleep_time=1,
        check_callback=lambda res: res.replace("\t", "|") == expected_result,
    )

    assert result_system_kafka_consumers.replace("\t", "|") == expected_result

    for format_name in [
        "Avro",
        "JSONEachRow",
    ]:
        k.kafka_delete_topic(admin_client, f"{format_name}_parsing_err")


def test_bad_messages_to_mv(kafka_cluster, max_retries=20):
    admin_client = KafkaAdminClient(
        bootstrap_servers="localhost:{}".format(kafka_cluster.kafka_port)
    )

    k.kafka_create_topic(admin_client, "tomv")

    instance.query(
        f"""
        DROP TABLE IF EXISTS kafka_materialized;
        DROP TABLE IF EXISTS kafka_consumer;
        DROP TABLE IF EXISTS kafka1;

        CREATE TABLE kafka1 (key UInt64, value String)
            ENGINE = Kafka
            SETTINGS kafka_broker_list = 'kafka1:19092',
                     kafka_topic_list = 'tomv',
                     kafka_group_name = 'tomv',
                     kafka_format = 'JSONEachRow',
                     kafka_flush_interval_ms=1000,
                     kafka_num_consumers = 1;

        CREATE TABLE kafka_materialized(`key` UInt64, `value` UInt64) ENGINE = Log;

        CREATE MATERIALIZED VIEW kafka_consumer TO kafka_materialized
        (`key` UInt64, `value` UInt64) AS
        SELECT key, CAST(value, 'UInt64') AS value
        FROM kafka1;
    """
    )

    k.kafka_produce(kafka_cluster, "tomv", ['{"key":10, "value":"aaa"}'])

    expected_result = """Code: 6. DB::Exception: Cannot parse string \\'aaa\\' as UInt64: syntax error at begin of string. Note: there are toUInt64OrZero and to|1|1|1|default|kafka1
"""
    result_system_kafka_consumers = instance.query_with_retry(
        """
        SELECT substr(exceptions.text[1], 1, 131), length(exceptions.text) > 1 AND length(exceptions.text) < 15, length(exceptions.time) > 1 AND length(exceptions.time) < 15, abs(dateDiff('second', exceptions.time[1], now())) < 40, database, table FROM system.kafka_consumers  WHERE table='kafka1' ORDER BY table, assignments.partition_id[1]
        """,
        retry_count=max_retries,
        sleep_time=1,
        check_callback=lambda res: res.replace("\t", "|") == expected_result,
    )

    assert result_system_kafka_consumers.replace("\t", "|") == expected_result

    k.kafka_delete_topic(admin_client, "tomv")


if __name__ == "__main__":
    cluster.start()
    input("Cluster created, press any key to destroy...")
    cluster.shutdown()
