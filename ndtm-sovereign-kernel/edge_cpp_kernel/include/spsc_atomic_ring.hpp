#pragma once

#include <atomic>
#include <cstddef>
#include <new>
#include <vector>
#include <type_traits>
#include <utility>

namespace ndtm::edge {

// Hardware destructive interference size (cache-line padding)
#ifdef __cpp_lib_hardware_interference_size
    using std::hardware_destructive_interference_size;
#else
    constexpr size_t hardware_destructive_interference_size = 64;
#endif

template <typename T, size_t Capacity = 65536>
class SPSCAtomicRingBuffer {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be a power of 2");
    static_assert(std::is_nothrow_move_constructible_v<T> || std::is_copy_constructible_v<T>,
                  "T must be nothrow move constructible or copy constructible");

public:
    SPSCAtomicRingBuffer() {
        buffer_ = static_cast<T*>(::operator new[](sizeof(T) * Capacity));
    }

    ~SPSCAtomicRingBuffer() {
        const size_t head = head_.load(std::memory_order_relaxed);
        const size_t tail = tail_.load(std::memory_order_relaxed);
        for (size_t i = head; i != tail; ++i) {
            buffer_[i & BufferMask].~T();
        }
        ::operator delete[](buffer_);
    }

    // Non-copyable, non-movable lock-free primitive
    SPSCAtomicRingBuffer(const SPSCAtomicRingBuffer&) = delete;
    SPSCAtomicRingBuffer& operator=(const SPSCAtomicRingBuffer&) = delete;
    SPSCAtomicRingBuffer(SPSCAtomicRingBuffer&&) = delete;
    SPSCAtomicRingBuffer& operator=(SPSCAtomicRingBuffer&&) = delete;

    template <typename... Args>
    bool emplace(Args&&... args) {
        const size_t current_tail = tail_.load(std::memory_order_relaxed);
        const size_t current_head = head_.load(std::memory_order_acquire);

        if ((current_tail - current_head) >= Capacity) {
            return false; // Buffer full
        }

        new (&buffer_[current_tail & BufferMask]) T(std::forward<Args>(args)...);
        tail_.store(current_tail + 1, std::memory_order_release);
        return true;
    }

    bool push(const T& item) {
        return emplace(item);
    }

    bool push(T&& item) {
        return emplace(std::move(item));
    }

    bool pop(T& item) {
        const size_t current_head = head_.load(std::memory_order_relaxed);
        const size_t current_tail = tail_.load(std::memory_order_acquire);

        if (current_head == current_tail) {
            return false; // Buffer empty
        }

        T* element = &buffer_[current_head & BufferMask];
        item = std::move(*element);
        element->~T();

        head_.store(current_head + 1, std::memory_order_release);
        return true;
    }

    [[nodiscard]] size_t size() const noexcept {
        const size_t current_tail = tail_.load(std::memory_order_acquire);
        const size_t current_head = head_.load(std::memory_order_acquire);
        return static_cast<size_t>(current_tail - current_head);
    }

    [[nodiscard]] bool empty() const noexcept {
        return head_.load(std::memory_order_acquire) == tail_.load(std::memory_order_acquire);
    }

    [[nodiscard]] bool full() const noexcept {
        return size() >= Capacity;
    }

    [[nodiscard]] constexpr size_t capacity() const noexcept {
        return Capacity;
    }

private:
    static constexpr size_t BufferMask = Capacity - 1;

    static constexpr size_t CACHE_LINE_SIZE = 64;
    alignas(CACHE_LINE_SIZE) std::atomic<size_t> tail_{0};
    uint8_t _padding1[CACHE_LINE_SIZE - sizeof(std::atomic<size_t>)]{0};

    alignas(CACHE_LINE_SIZE) std::atomic<size_t> head_{0};
    uint8_t _padding2[CACHE_LINE_SIZE - sizeof(std::atomic<size_t>)]{0};

    T* buffer_{nullptr};
};

} // namespace ndtm::edge
