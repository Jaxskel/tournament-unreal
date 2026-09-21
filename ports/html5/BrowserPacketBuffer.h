// Original bounded framing for UT's little-endian length-prefixed WS transport.
// Independent of Unreal headers so fragmentation/malformed input can be tested.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace TournamentHTML5 {
class PacketBuffer {
public:
    static const std::size_t MaxPacketBytes = 16384;

    // Callback data is borrowed until callback returns; copy it if retaining it.
    // The callback must not destroy or recursively call this parser.
    template<class Callback>
    bool Feed(const std::uint8_t* data, std::size_t size, Callback receive) {
        if (failed || (!data && size)) return Fail();
        while (size) {
            if (headerUsed < 4) {
                const std::size_t count = Min(size, 4 - headerUsed);
                std::memcpy(header + headerUsed, data, count);
                headerUsed += count; data += count; size -= count;
                if (headerUsed < 4) continue;
                length = std::uint32_t(header[0]) | (std::uint32_t(header[1]) << 8)
                    | (std::uint32_t(header[2]) << 16) | (std::uint32_t(header[3]) << 24);
                if (!length || length > MaxPacketBytes) return Fail();
            }
            const std::size_t count = Min(size, length - bodyUsed);
            std::memcpy(body + bodyUsed, data, count);
            bodyUsed += count; data += count; size -= count;
            if (bodyUsed == length) {
                receive(body, length);
                headerUsed = bodyUsed = length = 0;
            }
        }
        return true;
    }

    bool Failed() const { return failed; }
    std::size_t PendingBytes() const { return headerUsed + bodyUsed; }

private:
    static std::size_t Min(std::size_t a, std::size_t b) { return a < b ? a : b; }
    bool Fail() { failed = true; return false; }
    std::uint8_t header[4] = {};
    std::uint8_t body[MaxPacketBytes] = {};
    std::size_t headerUsed = 0, bodyUsed = 0, length = 0;
    bool failed = false;
};
}
