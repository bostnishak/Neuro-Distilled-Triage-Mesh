#pragma once

#include <atomic>
#include <array>
#include <cstddef>
#include <utility>

namespace ndtm::edge {

/**
 * @brief High-performance Single-Producer Single-Consumer (SPSC) Lock-Free Ring Buffer.
 * Guaranteed zero mutex locks and zero heap allocations on the hot telemetry ingestion path.
 * Aligned to 64-byte L1 cache line boundaries to prevent false sharing between core threads.
 *
 * @tparam T Type of elements stored in the buffer.
 * @tparam Capacity Total capacity (must be a power of 2).
 */
template <typename T, size_t Capacity>
class LockFreeRingBuffer {
    static_assert(Capacity >= 2, "Capacity must be at least 2.");
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be an exact power of 2.");

public:
    LockFreeRingBuffer() : head_(0), tail_(0) {}
    ~LockFreeRingBuffer() = default;

    // Non-copyable, non-movable for thread-safety guarantees
    LockFreeRingBuffer(const LockFreeRingBuffer&) = delete;
    LockFreeRingBuffer& operator=(const LockFreeRingBuffer&) = delete;

    /**
     * @brief Pushes an item into the ring buffer. Called exclusively by Producer thread.
     * @param item Item to be copied or moved into the buffer.
     * @return true if successfully pushed; false if buffer is completely full.
     */
    bool push(const T& item) {
        const size_t current_tail = tail_.load(std::memory_order_relaxed);
        const size_t current_head = head_.load(std::memory_order_acquire);

        if (current_tail - current_head >= Capacity) {
            return false; // Buffer overflow / backpressure
        }

        buffer_[current_tail & BufferMask] = item;
        tail_.store(current_tail + 1, std::memory_order_release);
        return true;
    }

    /**
     * @brief Pushes an r-value item into the ring buffer via move semantics.
     */
    bool push(T&& item) {
        const size_t current_tail = tail_.load(std::memory_order_relaxed);
        const size_t current_head = head_.load(std::memory_order_acquire);

        if (current_tail - current_head >= Capacity) {
            return false;
        }

        buffer_[current_tail & BufferMask] = std::move(item);
        tail_.store(current_tail + 1, std::memory_order_release);
        return true;
    }

    /**
     * @brief Pops an item from the ring buffer. Called exclusively by Consumer thread.
     * @param out_item Destination variable to store popped element.
     * @return true if an item was extracted; false if buffer is currently empty.
     */
    bool pop(T& out_item) {
        const size_t current_head = head_.load(std::memory_order_relaxed);
        const size_t current_tail = tail_.load(std::memory_order_acquire);

        if (current_head == current_tail) {
            return false; // Buffer underflow / hungry
        }

        out_item = std::move(buffer_[current_head & BufferMask]);
        head_.store(current_head + 1, std::memory_order_release);
        return true;
    }

    [[nodiscard]] size_t size() const noexcept {
        const size_t head = head_.load(std::memory_order_relaxed);
        const size_t tail = tail_.load(std::memory_order_relaxed);
        return (tail >= head) ? (tail - head) : 0;
    }

    [[nodiscard]] bool empty() const noexcept {
        return head_.load(std::memory_order_relaxed) == tail_.load(std::memory_order_relaxed);
    }

    [[nodiscard]] bool full() const noexcept {
        return size() >= Capacity;
    }

    [[nodiscard]] constexpr size_t capacity() const noexcept {
        return Capacity;
    }

private:
    static constexpr size_t BufferMask = Capacity - 1;

    // Cache-line aligned storage to prevent L1/L2 cache invalidation thrashing
    alignas(64) std::atomic<size_t> head_{0};
    alignas(64) std::atomic<size_t> tail_{0};
    alignas(64) std::array<T, Capacity> buffer_{};
};

} // namespace ndtm::edge
