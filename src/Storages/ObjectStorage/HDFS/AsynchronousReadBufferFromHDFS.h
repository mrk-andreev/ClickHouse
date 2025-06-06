#pragma once

#include "config.h"

#if USE_HDFS
#include <memory>

#    include <IO/AsynchronousReader.h>
#    include <IO/BufferWithOwnMemory.h>
#    include <IO/SeekableReadBuffer.h>
#    include <Storages/ObjectStorage/HDFS/ReadBufferFromHDFS.h>
#    include <base/types.h>

namespace DB
{

class IAsynchronousReader;
struct ReadSettings;

class AsynchronousReadBufferFromHDFS : public BufferWithOwnMemory<SeekableReadBuffer>, public WithFileName, public WithFileSize
{
public:
    AsynchronousReadBufferFromHDFS(
        IAsynchronousReader & reader_,
        const ReadSettings & settings_,
        std::shared_ptr<ReadBufferFromHDFS> impl_);

    ~AsynchronousReadBufferFromHDFS() override;

    off_t seek(off_t offset_, int whence) override;

    void prefetch(Priority priority) override;

    std::optional<size_t> tryGetFileSize() override;

    String getFileName() const override;

    off_t getPosition() override;

    size_t getFileOffsetOfBufferEnd() const override;

private:
    bool nextImpl() override;

    void finalize();

    bool hasPendingDataToRead();

    std::future<IAsynchronousReader::Result> asyncReadInto(char * data, size_t size, Priority priority);

    IAsynchronousReader & reader;
    Priority base_priority;
    std::shared_ptr<ReadBufferFromHDFS> impl;
    std::future<IAsynchronousReader::Result> prefetch_future;
    Memory<> prefetch_buffer;

    size_t file_offset_of_buffer_end = 0;
    std::optional<size_t> read_until_position;
    bool use_prefetch;

    LoggerPtr log;

    /// Metrics to profile prefetch
    Stopwatch interval_watch;
    Int64 sum_interval{0};
    Int64 sum_duration{0};
    Int64 sum_wait{0};
    Int64 next_times{0};
    Int64 seek_times{0};
};

}
#endif
