#!/usr/bin/env bash
# Tags: no-parallel-replicas, long

CUR_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../shell_config.sh
. "$CUR_DIR"/../shell_config.sh

# shellcheck source=./mergetree_mutations.lib
. "$CUR_DIR"/mergetree_mutations.lib

$CLICKHOUSE_CLIENT --query "
    DROP TABLE IF EXISTS t_rename_alter SYNC;

    CREATE TABLE t_rename_alter
    (
        id UInt64,
        dt DateTime DEFAULT now(),
        arr Array(Tuple(DateTime, UInt64, String, String)) TTL dt + INTERVAL 3 MONTHS
    )
    ENGINE = ReplicatedMergeTree('/clickhouse/tables/{database}/t_rename_alter', '1') ORDER BY id;

    INSERT INTO t_rename_alter (id) VALUES (1);
"

function insert1()
{
    while true; do
        $CLICKHOUSE_CLIENT --query "INSERT INTO t_rename_alter (id, dt, arr) SELECT 1, now(), [(now(), 1, 'a', 'b')]" --insert_deduplicate 0
        sleep 0.05
    done
}

function insert2()
{
    while true; do
        $CLICKHOUSE_CLIENT --query "INSERT INTO t_rename_alter (id, dt, arr_v2) SELECT 1, now(), [(now(), 1, 'a', 'b', 'c')]" --insert_deduplicate 0
        sleep 0.05
    done
}

function select1()
{
    while true; do
        $CLICKHOUSE_CLIENT --query "SELECT count() FROM t_rename_alter WHERE NOT ignore(*) FORMAT Null;" --insert_deduplicate 0
        sleep 0.05
    done
}

export -f insert1;
export -f insert2;
export -f select1;

TIMEOUT=8

for _ in {0..4}; do
    timeout $TIMEOUT bash -c insert1 2> /dev/null &
    timeout $TIMEOUT bash -c insert2 2> /dev/null &
    timeout $TIMEOUT bash -c select1 2> /dev/null &
done

$CLICKHOUSE_CLIENT --query "
    SET mutations_sync = 0;
    SET alter_sync = 0;

    SELECT sleep(randConstant() / toUInt32(-1)) * 0.1 FORMAT Null;

    ALTER TABLE t_rename_alter ADD COLUMN arr_v2 Array(Tuple(DateTime, UInt64, String, String, String)) DEFAULT [];

    SELECT sleep(randConstant() / toUInt32(-1)) * 0.1 FORMAT Null;

    ALTER TABLE t_rename_alter MODIFY COLUMN arr Array(Tuple(DateTime, UInt64, String, String)) DEFAULT [];

    SELECT sleep(randConstant() / toUInt32(-1)) * 0.1 FORMAT Null;

    ALTER TABLE t_rename_alter RENAME COLUMN arr TO arr_tmp;

    SELECT sleep(randConstant() / toUInt32(-1)) * 0.1 FORMAT Null;

    ALTER TABLE t_rename_alter RENAME COLUMN arr_v2 TO arr;

    SELECT sleep(randConstant() / toUInt32(-1)) * 0.1 FORMAT Null;

    OPTIMIZE TABLE t_rename_alter FINAL;
" 2>/dev/null
# Some concurrent alters may fail because of "Metadata on replica is not up to date with common metadata in Zookeeper"
# It is ok, we only check that server doesn't crash in this

wait

$CLICKHOUSE_CLIENT --query "
    ALTER TABLE t_rename_alter ADD COLUMN just_for_sync_alters_and_mutations UInt64 SETTINGS alter_sync = 2;
    ALTER TABLE t_rename_alter UPDATE just_for_sync_alters_and_mutations = 43 WHERE 1 SETTINGS mutations_sync = 2;
"

$CLICKHOUSE_CLIENT --query "
    SELECT count() > 0 FROM t_rename_alter WHERE NOT ignore(*);
    DROP TABLE IF EXISTS t_rename_alter SYNC;
"
