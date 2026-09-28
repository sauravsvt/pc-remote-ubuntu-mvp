param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('get', 'set', 'mute', 'unmute')]
  [string]$Action,
  [int]$Value = -1
)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace PcRemote {
  [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioEndpointVolume {
    int RegisterControlChangeNotify(IntPtr pNotify);
    int UnregisterControlChangeNotify(IntPtr pNotify);
    int GetChannelCount(out uint pnChannelCount);
    int SetMasterVolumeLevel(float fLevelDB, Guid pguidEventContext);
    int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
    int GetMasterVolumeLevel(out float pfLevelDB);
    int GetMasterVolumeLevelScalar(out float pfLevel);
    int SetChannelVolumeLevel(uint nChannel, float fLevelDB, Guid pguidEventContext);
    int SetChannelVolumeLevelScalar(uint nChannel, float fLevel, Guid pguidEventContext);
    int GetChannelVolumeLevel(uint nChannel, out float pfLevelDB);
    int GetChannelVolumeLevelScalar(uint nChannel, out float pfLevel);
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext);
    int GetMute([MarshalAs(UnmanagedType.Bool)] out bool pbMute);
  }

  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface);
  }

  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int dataFlow, uint dwStateMask, out IntPtr ppDevices);
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ppEndpoint);
  }

  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
  class MMDeviceEnumerator { }

  public static class Volume {
    static IAudioEndpointVolume Endpoint() {
      var enumerator = (IMMDeviceEnumerator)(object)new MMDeviceEnumerator();
      IMMDevice device;
      int hr = enumerator.GetDefaultAudioEndpoint(0, 0, out device);
      if (hr != 0) throw new System.ComponentModel.Win32Exception(hr);
      Guid iid = typeof(IAudioEndpointVolume).GUID;
      object endpoint;
      hr = device.Activate(ref iid, 23, IntPtr.Zero, out endpoint);
      if (hr != 0) throw new System.ComponentModel.Win32Exception(hr);
      return (IAudioEndpointVolume)endpoint;
    }

    public static string Get() {
      var endpoint = Endpoint();
      float level;
      bool mute;
      int hr = endpoint.GetMasterVolumeLevelScalar(out level);
      if (hr != 0) throw new System.ComponentModel.Win32Exception(hr);
      hr = endpoint.GetMute(out mute);
      if (hr != 0) throw new System.ComponentModel.Win32Exception(hr);
      int percent = (int)Math.Round(level * 100.0);
      return percent.ToString() + (mute ? " 1" : " 0");
    }

    public static void Set(int value) {
      if (value < 0 || value > 100) throw new ArgumentOutOfRangeException("value");
      int hr = Endpoint().SetMasterVolumeLevelScalar(value / 100.0f, Guid.Empty);
      if (hr != 0) throw new System.ComponentModel.Win32Exception(hr);
    }

    public static void Mute(bool muted) {
      int hr = Endpoint().SetMute(muted, Guid.Empty);
      if (hr != 0) throw new System.ComponentModel.Win32Exception(hr);
    }
  }
}
'@
switch ($Action) {
  'get' { [PcRemote.Volume]::Get() }
  'set' { [PcRemote.Volume]::Set($Value) }
  'mute' { [PcRemote.Volume]::Mute($true) }
  'unmute' { [PcRemote.Volume]::Mute($false) }
}
