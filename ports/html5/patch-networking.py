"""Install original browser-only transport fixes into the isolated legacy port.

The native experimental libwebsockets server is not hardened by these changes.
Use a separately validated gateway for public admission; this is not a production
readiness claim. Run only while the compiler is stopped.
"""
from pathlib import Path
import argparse
import json
import re
import shutil

RECEIVE = r'''
    // Tournament browser framing: signed recv results, partial packet retention,
    // bounded reads per tick, no unaligned length dereference or negative cast.
    if (TournamentClosed || SockFd < 0) return;
    uint8 Chunk[16384];
    for (int32 Batch = 0; Batch < 64; ++Batch)
    {
        const int Count = recv(SockFd, Chunk, sizeof(Chunk), 0);
        if (Count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) return;
        if (Count <= 0 || !TournamentReceive.Feed(Chunk, Count,
            [this](const uint8* Packet, size_t Length) {
                if (!TournamentClosed) RecievedCallBack.ExecuteIfBound((void*)Packet, (uint32)Length);
            }))
        {
            TournamentClosed = true;
            close(SockFd); SockFd = -1;
            OutgoingBuffer.Empty(); TournamentSendOffset = 0;
            return;
        }
        if (TournamentClosed) return;
    }
'''

SEND = r'''
    // Tournament browser writes: retain the unsent tail on backpressure.
    // A zero/partial write cannot spin or point before the beginning of Packet.
    if (TournamentClosed || SockFd < 0) return;
    const int Result = send(SockFd, Packet.GetData() + TournamentSendOffset,
        Packet.Num() - TournamentSendOffset, 0);
    if (Result < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) return;
    if (Result <= 0)
    {
        TournamentClosed = true;
        close(SockFd); SockFd = -1;
        OutgoingBuffer.Empty(); TournamentSendOffset = 0;
        return;
    }
    TournamentSendOffset += Result;
    if (TournamentSendOffset < (uint32)Packet.Num()) return;
    TournamentSendOffset = 0;
'''


def prepare(path, transform):
    """Validate against the original backup before any file in the set changes."""
    backup = path.with_suffix(path.suffix + '.before-tournament-html5')
    text = path.read_text(encoding='utf-8-sig')
    original = backup.read_text(encoding='utf-8-sig') if backup.exists() else text
    if any(marker in original for marker in (
            'TournamentReceive', 'Tournament browser framing',
            'Tournament browser disconnect', 'TournamentFailurePending')):
        raise ValueError(f'Original networking backup required: {path.name}')
    updated = transform(original)
    if text not in (original, updated):
        raise ValueError(f'Networking source conflicts with backup: {path.name}')
    return path, backup, text, updated


def replace_one(text, before, after):
    if text.count(before) != 1:
        raise ValueError(f'Unexpected networking source anchor: {before}')
    return text.replace(before, after)


def replace_browser_branch(text, method, replacement):
    signature = 'void FWebSocket::' + method
    if text.count(signature) != 1:
        raise ValueError(f'Unexpected networking method: {method}')
    start = text.index(signature)
    # Constructors/destructors have no return type and also delimit a method.
    following = re.search(r'\n(?:[\w:*<>]+[ \t]+)?FWebSocket::', text[start + len(signature):])
    limit = start + len(signature) + following.start() if following else len(text)
    branch = text[start:limit]
    if branch.count('#else // PLATFORM_HTML5') != 1:
        raise ValueError(f'Unexpected browser branch: {method}')
    start = text.index('#else // PLATFORM_HTML5', start, limit)
    start = text.index('\n', start) + 1
    end = text.index('#endif', start, limit)
    return text[:start] + replacement + '\n' + text[end:]


def patch(root):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Refusing unmarked source checkout')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if (version.get('MajorVersion'), version.get('MinorVersion'), version.get('Changelist')) != (4, 15, 3228288):
        raise ValueError('Unsupported engine revision')
    folder = root / 'Engine/Plugins/Experimental/HTML5Networking/Source/HTML5Networking/Private'
    packet_header = Path(__file__).with_name('BrowserPacketBuffer.h').read_bytes()
    destination = folder / 'BrowserPacketBuffer.h'
    if destination.is_dir():
        raise ValueError('BrowserPacketBuffer.h destination is a directory')
    current_packet_header = destination.read_bytes() if destination.exists() else None

    def header(text):
        text = replace_one(text, '#include <netinet/in.h>', '#include <netinet/in.h>\n#include "BrowserPacketBuffer.h"')
        return replace_one(text, '\tint SockFd;', '''\tint SockFd;
    TournamentHTML5::PacketBuffer TournamentReceive;
    uint32 TournamentSendOffset = 0;
    bool TournamentClosed = false;
    bool TournamentFailureNotified = false;''')

    def implementation(text):
        text = replace_browser_branch(text, 'OnRawRecieve(', RECEIVE)
        text = replace_browser_branch(text, 'OnRawWebSocketWritable(', SEND)
        text = replace_browser_branch(text, 'HandlePacket()', r"""
    // Emscripten recv/send are nonblocking and select only supports 64 fds.
    // Defer failure notification until Tick, outside a possibly reentrant Send.
    if (TournamentClosed || SockFd < 0)
    {
        TournamentClosed = true;
        if (!TournamentFailureNotified)
        {
            TournamentFailureNotified = true;
            ErrorCallBack.ExecuteIfBound();
        }
        return;
    }
    OnRawRecieve(NULL, 0);
    for (int32 Batch = 0; !TournamentClosed && Batch < 64 && OutgoingBuffer.Num() > 0; ++Batch)
    {
        const int32 PreviousCount = OutgoingBuffer.Num();
        const uint32 PreviousOffset = TournamentSendOffset;
        OnRawWebSocketWritable(NULL);
        if (OutgoingBuffer.Num() == PreviousCount && TournamentSendOffset == PreviousOffset) break;
    }
""")
        anchor = 'bool FWebSocket::Send(uint8* Data, uint32 Size)\n{'
        if text.count(anchor) != 1:
            raise ValueError('Unexpected Send function')
        text = text.replace(anchor, anchor + '''
#if PLATFORM_HTML5_BROWSER
    if (TournamentClosed || Size == 0 || Size > TournamentHTML5::PacketBuffer::MaxPacketBytes
        || OutgoingBuffer.Num() >= 128)
    {
        TournamentClosed = true;
        if (SockFd >= 0) { close(SockFd); SockFd = -1; }
        OutgoingBuffer.Empty(); TournamentSendOffset = 0;
        return false;
    }
#endif
''')
        text = text.replace('\tclose(SockFd);', '\tif (SockFd >= 0) close(SockFd);')
        return text

    def driver(text):
        anchor = '\tConnection->SetWebSocket(WebSocket);'
        if text.count(anchor) != 1:
            raise ValueError('Unexpected local WebSocket binding')
        text = text.replace(anchor, anchor + '''
#if PLATFORM_HTML5_BROWSER
    // Tournament browser disconnect: close the game connection on socket failure.
    const TWeakObjectPtr<UWebSocketNetDriver> WeakDriver(this);
    FWebsocketInfoCallBack SocketError;
    SocketError.BindLambda([WeakDriver]() {
        if (WeakDriver.IsValid()) WeakDriver->TournamentFailurePending = true;
    });
    WebSocket->SetErrorCallBack(SocketError);
#endif
''')

        text = replace_one(text, '#include "WebSocketNetDriver.h"',
            '#include "WebSocketNetDriver.h"\n#include "Engine/Engine.h"\n#include "EngineGlobals.h"')
        tick = 'void UWebSocketNetDriver::TickDispatch(float DeltaTime)\n{'
        if text.count(tick) != 1:
            raise ValueError('Unexpected TickDispatch function')
        return text.replace(tick, tick + r'''
#if PLATFORM_HTML5_BROWSER
    // Broadcast only from driver dispatch, never from inside packet callbacks.
    if (TournamentFailurePending)
    {
        TournamentFailurePending = false;
        GEngine->BroadcastNetworkFailure(GetWorld(), this, ENetworkFailure::ConnectionLost,
            TEXT("Browser game connection closed. Please reconnect."));
        return; // the broadcast may synchronously destroy this driver
    }
#endif
''')

    def driver_header(text):
        anchor = '\tint32 WebSocketPort;'
        if text.count(anchor) != 1:
            raise ValueError('Unexpected driver header')
        return text.replace(anchor, anchor + '\n#if PLATFORM_HTML5_BROWSER\n    bool TournamentFailurePending = false;\n#endif')

    plans = [
        prepare(folder / 'WebSocket.h', header),
        prepare(folder / 'WebSocket.cpp', implementation),
        prepare(folder / 'WebSocketNetDriver.cpp', driver),
        prepare(folder.parent / 'Classes/WebSocketNetDriver.h', driver_header),
    ]
    # All source/backup guards passed. Keep the old backup names and output text.
    for path, backup, text, updated in plans:
        if updated != text:
            if not backup.exists():
                shutil.copy2(path, backup)
            path.write_text(updated, encoding='utf-8')
    if current_packet_header != packet_header:
        destination.write_bytes(packet_header)
    print('Installed bounded browser packet framing and partial-write/disconnect fixes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root')
    patch(parser.parse_args().source_root)
