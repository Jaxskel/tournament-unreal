"""Opt-in offscreen viewport patch for a licensed local UE4.15 source installation.
Only modifies D3D11 viewport creation; no desktop capture or OS input control.
Stop every process using this installation before patching/building.
"""
import argparse, json
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument("source_root", type=Path)
args=parser.parse_args()
root=args.source_root
version=json.loads((root/"Engine/Build/Build.version").read_text(encoding="utf-8-sig"))
if (version["MajorVersion"], version["MinorVersion"], version["Changelist"]) != (4,15,3228288):
    raise SystemExit("Expected recovered UE4.15 CL3228288 source. No files changed.")
private=root/"Engine/Source/Runtime/Windows/D3D11RHI/Private"
win=private/"Windows/WindowsD3D11Viewport.cpp"
base=private/"D3D11Viewport.cpp"
w=win.read_text(); b=base.read_text()
if "TournamentOffscreen" in w:
    raise SystemExit("Offscreen patch already present; no changes.")
if "CreateSwapChain" not in w or "GetSwapChainSurface" not in b:
    raise SystemExit("Unexpected source layout; no files changed.")
for target in (win, base):
    backup=target.with_suffix(target.suffix+".tournament-original")
    if backup.exists(): raise SystemExit(f"Existing backup: {backup}; inspect before patching.")
for target in (win, base):
    target.with_suffix(target.suffix+".tournament-original").write_bytes(target.read_bytes())
w=w.replace('IDXGISwapChain* SwapChain);','IDXGISwapChain* SwapChain, uint32 Width, uint32 Height);')
w=w.replace('\t// Create a backbuffer/swapchain for each viewport','''\t// Tournament: explicit GPU-only viewport for browser clients in Windows session zero.
\tif (FParse::Param(FCommandLine::Get(), TEXT("TournamentOffscreen")))
\t{
\t\tbIsFullscreen = false;
\t\tBackBuffer = GetSwapChainSurface(D3DRHI, PixelFormat, nullptr, SizeX, SizeY);
\t\tBeginInitResource(&FrameSyncEvent);
\t\treturn;
\t}

\t// Create a backbuffer/swapchain for each viewport''')
w=w.replace('void FD3D11Viewport::ConditionalResetSwapChain(bool bIgnoreFocus)\n{','void FD3D11Viewport::ConditionalResetSwapChain(bool bIgnoreFocus)\n{\n\tif (!SwapChain) return;')
b=b.replace('IDXGISwapChain* SwapChain)\n{','IDXGISwapChain* SwapChain, uint32 Width, uint32 Height)\n{',1)
old='\tVERIFYD3D11RESULT_EX(SwapChain->GetBuffer(0,IID_ID3D11Texture2D,(void**)BackBufferResource.GetInitReference()), D3DRHI->GetDevice());'
b=b.replace(old,'''\tif (SwapChain)
\t{
'''+old+'''
\t}
\telse
\t{
\t\tD3D11_TEXTURE2D_DESC Desc = {};
\t\tDesc.Width = Width; Desc.Height = Height;
\t\tDesc.MipLevels = 1; Desc.ArraySize = 1;
\t\tDesc.Format = GetRenderTargetFormat(PixelFormat);
\t\tDesc.SampleDesc.Count = 1;
\t\tDesc.Usage = D3D11_USAGE_DEFAULT;
\t\tDesc.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
\t\tVERIFYD3D11RESULT_EX(D3DRHI->GetDevice()->CreateTexture2D(&Desc, nullptr, BackBufferResource.GetInitReference()), D3DRHI->GetDevice());
\t}''')
b=b.replace('\tVERIFYD3D11RESULT_EX(SwapChain->SetFullscreenState(false,NULL), D3DRHI->GetDevice());','\tif (SwapChain) { VERIFYD3D11RESULT_EX(SwapChain->SetFullscreenState(false,NULL), D3DRHI->GetDevice()); }')
b=b.replace('\t// Release our backbuffer reference, as required by DXGI before calling ResizeBuffers.','''\tif (!SwapChain)
\t{
\t\tBackBuffer.SafeRelease();
\t\tSizeX = InSizeX; SizeY = InSizeY;
\t\tif (PreferredPixelFormat != PF_Unknown) PixelFormat = PreferredPixelFormat;
\t\tbIsFullscreen = false;
\t\tBackBuffer = GetSwapChainSurface(D3DRHI, PixelFormat, nullptr, SizeX, SizeY);
\t\treturn;
\t}
\t// Release our backbuffer reference, as required by DXGI before calling ResizeBuffers.''')
b=b.replace('bool FD3D11Viewport::Present(bool bLockToVsync)\n{','bool FD3D11Viewport::Present(bool bLockToVsync)\n{\n\tif (!SwapChain) { D3DRHI->GetDeviceContext()->Flush(); return false; }')
w=w.replace("GetSwapChainSurface(D3DRHI, PixelFormat, SwapChain);", "GetSwapChainSurface(D3DRHI, PixelFormat, SwapChain, SizeX, SizeY);")
b=b.replace("GetSwapChainSurface(D3DRHI, PixelFormat, SwapChain);", "GetSwapChainSurface(D3DRHI, PixelFormat, SwapChain, SizeX, SizeY);")
win.write_text(w)
base.write_text(b)
print("Patched D3D11 viewport. Original files saved as .tournament-original; rebuild D3D11RHI before using -TournamentOffscreen.")
