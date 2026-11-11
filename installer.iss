[Setup]
AppName=SirJoe VPN
AppVersion=1.0
DefaultDirName={autopf}\SirJoe VPN
DefaultGroupName=SirJoe VPN
OutputDir=Output
OutputBaseFilename=SirJoeVPN-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest

[Files]
Source: "dist\SirJoeVPN.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SirJoe VPN"; Filename: "{app}\SirJoeVPN.exe"
Name: "{autodesktop}\SirJoe VPN"; Filename: "{app}\SirJoeVPN.exe"

[Run]
Filename: "{app}\SirJoeVPN.exe"; Description: "Avvia SirJoe VPN"; Flags: nowait postinstall skipifsilent
