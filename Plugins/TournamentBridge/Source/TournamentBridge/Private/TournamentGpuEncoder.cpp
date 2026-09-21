#include "TournamentBridgeMutator.h"
#include "TournamentGpuEncoder.h"
#if PLATFORM_WINDOWS
// Preserve UE4/OnlineSubsystem definitions around the Windows SDK headers.
#pragma push_macro("ERROR_SUCCESS")
#pragma push_macro("ERROR_IO_PENDING")
#pragma push_macro("E_NOTIMPL")
#pragma push_macro("E_FAIL")
#undef ERROR_SUCCESS
#undef ERROR_IO_PENDING
#undef E_NOTIMPL
#undef E_FAIL
#include "Windows/AllowWindowsPlatformTypes.h"
#include <d3d11.h>
#include "../../ThirdParty/NVENC/nvEncodeAPI.h"
#include "Windows/HideWindowsPlatformTypes.h"
#pragma pop_macro("E_FAIL")
#pragma pop_macro("E_NOTIMPL")
#pragma pop_macro("ERROR_IO_PENDING")
#pragma pop_macro("ERROR_SUCCESS")

struct FTournamentGpuEncoder::FImpl
{
    void* Library = nullptr;
    NV_ENCODE_API_FUNCTION_LIST API = {};
    void* Session = nullptr;
    ID3D11Device* Device = nullptr;
    ID3D11DeviceContext* Context = nullptr;
    ID3D11Texture2D* Input = nullptr;
    NV_ENC_REGISTERED_PTR Registered = nullptr;
    NV_ENC_INPUT_PTR Mapped = nullptr;
    NV_ENC_OUTPUT_PTR Output = nullptr;
    NV_ENC_BUFFER_FORMAT Format = NV_ENC_BUFFER_FORMAT_UNDEFINED;
    uint32 Width = 0, Height = 0, Rate = 0;
    uint64 Sequence = 0;

    ~FImpl()
    {
        if (Session)
        {
            if (Mapped) API.nvEncUnmapInputResource(Session, Mapped);
            if (Output) API.nvEncDestroyBitstreamBuffer(Session, Output);
            if (Registered) API.nvEncUnregisterResource(Session, Registered);
            API.nvEncDestroyEncoder(Session);
        }
        if (Input) Input->Release();
        if (Context) Context->Release();
        if (Device) Device->Release();
        if (Library) FPlatformProcess::FreeDllHandle(Library);
    }
    bool Check(NVENCSTATUS Status, const TCHAR* Operation, FString& Error)
    {
        if (Status == NV_ENC_SUCCESS) return true;
        const char* Detail = Session && API.nvEncGetLastErrorString ? API.nvEncGetLastErrorString(Session) : nullptr;
        Error = FString::Printf(TEXT("NVENC %s failed (%d): %s"), Operation, int32(Status), Detail ? UTF8_TO_TCHAR(Detail) : TEXT("no driver detail"));
        return false;
    }
    bool Open(ID3D11Texture2D* Source, uint32 FPS, FString& Error)
    {
        D3D11_TEXTURE2D_DESC Desc = {};
        Source->GetDesc(&Desc);
        Width = Desc.Width; Height = Desc.Height; Rate = FPS;
        if (Width > 2560 || Height > 1440 || Desc.SampleDesc.Count != 1)
        { Error = TEXT("Unsupported GPU capture dimensions or multisampling"); return false; }
        if (Desc.Format == DXGI_FORMAT_B8G8R8A8_UNORM || Desc.Format == DXGI_FORMAT_B8G8R8A8_TYPELESS || Desc.Format == DXGI_FORMAT_B8G8R8A8_UNORM_SRGB)
        { Format = NV_ENC_BUFFER_FORMAT_ARGB; Desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM; }
        else if (Desc.Format == DXGI_FORMAT_R8G8B8A8_UNORM || Desc.Format == DXGI_FORMAT_R8G8B8A8_TYPELESS || Desc.Format == DXGI_FORMAT_R8G8B8A8_UNORM_SRGB)
        { Format = NV_ENC_BUFFER_FORMAT_ABGR; Desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM; }
        else if (Desc.Format == DXGI_FORMAT_R10G10B10A2_UNORM)
        { Format = NV_ENC_BUFFER_FORMAT_ABGR10; }
        else { Error = FString::Printf(TEXT("Unsupported backbuffer format %d"), int32(Desc.Format)); return false; }

        // Load the installed driver from Windows' system directory, never game content.
        WCHAR SystemDirectory[MAX_PATH] = {};
        const UINT PathLength = GetSystemDirectoryW(SystemDirectory, MAX_PATH);
        if (!PathLength || PathLength >= MAX_PATH) { Error = TEXT("Cannot find Windows system directory"); return false; }
        Library = FPlatformProcess::GetDllHandle(*(FString(SystemDirectory) / TEXT("nvEncodeAPI64.dll")));
        if (!Library) { Error = TEXT("The NVIDIA encoding driver is unavailable"); return false; }
        typedef NVENCSTATUS (NVENCAPI *FCreateAPI)(NV_ENCODE_API_FUNCTION_LIST*);
        FCreateAPI Create = reinterpret_cast<FCreateAPI>(FPlatformProcess::GetDllExport(Library, TEXT("NvEncodeAPICreateInstance")));
        if (!Create) { Error = TEXT("The NVIDIA driver has no encoder API"); return false; }
        API.version = NV_ENCODE_API_FUNCTION_LIST_VER;
        if (!Check(Create(&API), TEXT("create API"), Error)) return false;
        Source->GetDevice(&Device);
        Device->GetImmediateContext(&Context);
        NV_ENC_OPEN_ENCODE_SESSION_EX_PARAMS OpenParams = {};
        OpenParams.version = NV_ENC_OPEN_ENCODE_SESSION_EX_PARAMS_VER;
        OpenParams.deviceType = NV_ENC_DEVICE_TYPE_DIRECTX;
        OpenParams.device = Device; OpenParams.apiVersion = NVENCAPI_VERSION;
        if (!Check(API.nvEncOpenEncodeSessionEx(&OpenParams, &Session), TEXT("open session"), Error)) return false;
        NV_ENC_PRESET_CONFIG Preset = {};
        Preset.version = NV_ENC_PRESET_CONFIG_VER; Preset.presetCfg.version = NV_ENC_CONFIG_VER;
        if (!Check(API.nvEncGetEncodePresetConfigEx(Session, NV_ENC_CODEC_H264_GUID, NV_ENC_PRESET_P3_GUID,
            NV_ENC_TUNING_INFO_ULTRA_LOW_LATENCY, &Preset), TEXT("preset"), Error)) return false;
        NV_ENC_CONFIG Config = Preset.presetCfg;
        Config.profileGUID = NV_ENC_H264_PROFILE_HIGH_GUID;
        Config.gopLength = 10; Config.frameIntervalP = 1;
        Config.rcParams.rateControlMode = NV_ENC_PARAMS_RC_CBR;
        const uint32 Mbps = Height == 1440 ? (FPS == 120 ? 40 : 28) : Height == 1080 ? (FPS == 120 ? 24 : 16)
            : Height == 720 ? (FPS == 120 ? 12 : 8) : (FPS == 120 ? 6 : 4);
        Config.rcParams.averageBitRate = Config.rcParams.maxBitRate = Mbps * 1000000;
        Config.rcParams.vbvBufferSize = Mbps * 32000;
        Config.rcParams.vbvInitialDelay = Config.rcParams.vbvBufferSize;
        Config.rcParams.enableLookahead = 0; Config.rcParams.lookaheadDepth = 0;
        Config.rcParams.zeroReorderDelay = 1;
        Config.encodeCodecConfig.h264Config.idrPeriod = 10;
        Config.encodeCodecConfig.h264Config.repeatSPSPPS = 1;
        Config.encodeCodecConfig.h264Config.outputAUD = 1;
        NV_ENC_INITIALIZE_PARAMS Init = {};
        Init.version = NV_ENC_INITIALIZE_PARAMS_VER;
        Init.encodeGUID = NV_ENC_CODEC_H264_GUID; Init.presetGUID = NV_ENC_PRESET_P3_GUID;
        Init.encodeWidth = Init.darWidth = Init.maxEncodeWidth = Width;
        Init.encodeHeight = Init.darHeight = Init.maxEncodeHeight = Height;
        Init.frameRateNum = FPS; Init.frameRateDen = 1;
        Init.enablePTD = 1; Init.enableEncodeAsync = 0;
        Init.tuningInfo = NV_ENC_TUNING_INFO_ULTRA_LOW_LATENCY;
        Init.encodeConfig = &Config;
        if (!Check(API.nvEncInitializeEncoder(Session, &Init), TEXT("initialize"), Error)) return false;
        // A private GPU texture keeps renderer ownership independent from the NVENC mapping.
        // No staging allocation, CPU readback, RGB conversion or raw TCP transfer.
        Desc.Usage = D3D11_USAGE_DEFAULT; Desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        Desc.CPUAccessFlags = 0; Desc.MiscFlags = 0; Desc.MipLevels = Desc.ArraySize = 1;
        if (FAILED(Device->CreateTexture2D(&Desc, nullptr, &Input))) { Error = TEXT("Cannot allocate encoder GPU texture"); return false; }
        NV_ENC_REGISTER_RESOURCE Register = {};
        Register.version = NV_ENC_REGISTER_RESOURCE_VER;
        Register.resourceType = NV_ENC_INPUT_RESOURCE_TYPE_DIRECTX;
        Register.width = Width; Register.height = Height;
        Register.resourceToRegister = Input; Register.bufferFormat = Format;
        Register.bufferUsage = NV_ENC_INPUT_IMAGE;
        if (!Check(API.nvEncRegisterResource(Session, &Register), TEXT("register GPU texture"), Error)) return false;
        Registered = Register.registeredResource;
        NV_ENC_CREATE_BITSTREAM_BUFFER CreateBuffer = {};
        CreateBuffer.version = NV_ENC_CREATE_BITSTREAM_BUFFER_VER;
        if (!Check(API.nvEncCreateBitstreamBuffer(Session, &CreateBuffer), TEXT("output buffer"), Error)) return false;
        Output = CreateBuffer.bitstreamBuffer;
        return true;
    }
    bool Encode(ID3D11Texture2D* Source, TArray<uint8>& Packet, FString& Error)
    {
        Context->CopyResource(Input, Source);
        NV_ENC_MAP_INPUT_RESOURCE Map = {};
        Map.version = NV_ENC_MAP_INPUT_RESOURCE_VER; Map.registeredResource = Registered;
        if (!Check(API.nvEncMapInputResource(Session, &Map), TEXT("map GPU texture"), Error)) return false;
        Mapped = Map.mappedResource;
        NV_ENC_PIC_PARAMS Picture = {};
        Picture.version = NV_ENC_PIC_PARAMS_VER;
        Picture.inputBuffer = Mapped; Picture.bufferFmt = Format;
        Picture.inputWidth = Width; Picture.inputHeight = Height;
        Picture.outputBitstream = Output; Picture.pictureStruct = NV_ENC_PIC_STRUCT_FRAME;
        Picture.inputTimeStamp = ++Sequence;
        if (!Check(API.nvEncEncodePicture(Session, &Picture), TEXT("encode"), Error)) return false;
        NV_ENC_LOCK_BITSTREAM Lock = {};
        Lock.version = NV_ENC_LOCK_BITSTREAM_VER; Lock.outputBitstream = Output;
        if (!Check(API.nvEncLockBitstream(Session, &Lock), TEXT("read compressed output"), Error)) return false;
        const uint32 Length = Lock.bitstreamSizeInBytes;
        const bool Valid = Length >= 4 && Length <= 4 * 1024 * 1024 - 16;
        if (Valid)
        {
            Packet.SetNumUninitialized(Length + 12);
            Packet[0] = 'T'; Packet[1] = 'N'; Packet[2] = 'V'; Packet[3] = 1;
            Packet[4] = uint8(Width >> 8); Packet[5] = uint8(Width);
            Packet[6] = uint8(Height >> 8); Packet[7] = uint8(Height);
            Packet[8] = uint8(Rate >> 8); Packet[9] = uint8(Rate);
            Packet[10] = Packet[11] = 0;
            FMemory::Memcpy(Packet.GetData() + 12, Lock.bitstreamBufferPtr, Length);
        }
        const NVENCSTATUS Unlocked = API.nvEncUnlockBitstream(Session, Output);
        const NVENCSTATUS Unmapped = API.nvEncUnmapInputResource(Session, Mapped);
        if (Unmapped == NV_ENC_SUCCESS) Mapped = nullptr;
        if (!Valid) { Error = TEXT("Invalid compressed frame size"); return false; }
        return Check(Unlocked, TEXT("unlock output"), Error) && Check(Unmapped, TEXT("unmap GPU texture"), Error);
    }
};
#else
struct FTournamentGpuEncoder::FImpl {};
#endif

FTournamentGpuEncoder::FTournamentGpuEncoder() : Impl(nullptr) {}
FTournamentGpuEncoder::~FTournamentGpuEncoder() { delete Impl; }
bool FTournamentGpuEncoder::Encode(FTexture2DRHIRef Texture, int32 FPS, TArray<uint8>& Packet, FString& Error)
{
#if PLATFORM_WINDOWS
    ID3D11Texture2D* Source = Texture.IsValid() ? static_cast<ID3D11Texture2D*>(Texture->GetNativeResource()) : nullptr;
    if (!Source) { Error = TEXT("No D3D11 game texture available"); return false; }
    D3D11_TEXTURE2D_DESC Desc = {}; Source->GetDesc(&Desc);
    if (Impl && (Desc.Width != Impl->Width || Desc.Height != Impl->Height || uint32(FPS) != Impl->Rate)) { delete Impl; Impl = nullptr; }
    if (!Impl)
    {
        Impl = new FImpl();
        if (!Impl->Open(Source, FPS, Error)) { delete Impl; Impl = nullptr; return false; }
    }
    if (Impl->Encode(Source, Packet, Error)) return true;
    delete Impl; Impl = nullptr; return false;
#else
    Error = TEXT("Direct GPU encoding requires Windows D3D11 and an NVIDIA driver"); return false;
#endif
}
