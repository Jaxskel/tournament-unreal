#include "BrowserPacketBuffer.h"
#include <algorithm>
#include <cstdlib>
#define CHECK(condition) do { if (!(condition)) { std::cerr << "Failed: " #condition << " at " << __LINE__ << "\n"; std::exit(1); } } while (false)
#include <vector>
#include <iostream>

using Bytes = std::vector<std::uint8_t>;
using Packets = std::vector<Bytes>;
using TournamentHTML5::PacketBuffer;

static Bytes Wire(const Packets& packets) {
    Bytes result;
    for (const auto& packet : packets) {
        for (unsigned shift = 0; shift < 32; shift += 8)
            result.push_back(static_cast<std::uint8_t>(packet.size() >> shift));
        result.insert(result.end(), packet.begin(), packet.end());
    }
    return result;
}

int main() {
    const Packets expected = { {1}, Bytes(512, 42), {9, 8, 7}, Bytes(16384, 65) };
    const Bytes wire = Wire(expected);
    // All split points cover partial headers/bodies and coalesced packets.
    for (std::size_t split = 0; split <= wire.size(); ++split) {
        PacketBuffer buffer;
        Packets actual;
        auto receive = [&](const std::uint8_t* data, std::size_t size) {
            actual.emplace_back(data, data + size);
        };
        CHECK(buffer.Feed(wire.data(), split, receive));
        CHECK(buffer.Feed(wire.data() + split, wire.size() - split, receive));
        CHECK(actual == expected);
        CHECK(buffer.PendingBytes() == 0);
    }
    // Arbitrary repeated fragmentation, not just one split per stream.
    for (std::size_t chunk = 1; chunk < 1024; chunk += 13) {
        PacketBuffer buffer; Packets actual;
        for (std::size_t offset = 0; offset < wire.size();) {
            const std::size_t count = std::min(chunk, wire.size() - offset);
            CHECK(buffer.Feed(wire.data() + offset, count,
                [&](const std::uint8_t* data, std::size_t size) { actual.emplace_back(data, data + size); }));
            offset += count;
        }
        CHECK(actual == expected);
    }
    // Zero, oversized, and signed-negative-looking lengths fail before payload.
    for (const Bytes& header : {Bytes{0,0,0,0}, Bytes{1,64,0,0}, Bytes{255,255,255,255}}) {
        PacketBuffer buffer;
        auto reject = [](const std::uint8_t*, std::size_t) { CHECK(false); };
        CHECK(!buffer.Feed(header.data(), header.size(), reject));
        CHECK(buffer.Failed());
        CHECK(!buffer.Feed(wire.data(), wire.size(), reject));
    }
    PacketBuffer invalid;
    CHECK(!invalid.Feed(nullptr, 1, [](const std::uint8_t*, std::size_t) {}));
    std::cout << "Packet framing: all boundaries, fragments, coalescing and invalid lengths passed\n";
}
