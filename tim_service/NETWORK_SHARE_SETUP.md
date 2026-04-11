# Network Share Setup Guide

If you want to **edit TIM service files from your laptop** while the code lives on iPC400, set up a network share.

## Windows Network Share Setup

### On iPC400 (TIM-PC):

1. **Create a shared folder**:
   - Right-click `C:\TIM\tim_service` → Properties
   - Go to Sharing tab → Advanced Sharing
   - Check "Share this folder"
   - Set share name (e.g., `TIM_Service`)
   - Click Permissions → Grant Read/Write to Everyone (or specific user)

2. **Note the network path**:
   - `\\<iPC400-IP-OR-NAME>\TIM_Service`
   - Example: `\\192.168.1.100\TIM_Service` or `\\TIM-PC\TIM_Service`

### On Your Laptop (GUI PC):

1. **Map network drive** (optional, for convenience):
   - File Explorer → "This PC" → Map network drive
   - Drive letter: `Z:` (or your choice)
   - Path: `\\192.168.1.100\TIM_Service` (use iPC400 IP or hostname)
   - Click Finish
   - Now you can browse Z:\ in File Explorer and VS Code

2. **Or open directly in VS Code**:
   - File → Open Folder
   - Type `\\192.168.1.100\TIM_Service` in the path
   - Click Select Folder
   - VS Code opens the remote share as if it were local

### Permissions Note

- Ensure iPC400 user and your laptop user have matching credentials, or
- Set share permissions to allow your Windows user (if on same domain)
- For simple setups, enable guest access (less secure but easier)

## SSH Alternative (Linux/Mac on iPC400, Phase 3)

When iPC400 migrates to Linux for real-time kernel:

```bash
# On your laptop, use VS Code Remote SSH
# Install "Remote - SSH" extension in VS Code

# Then in VS Code:
# File → Open Remote Window → Connect to Host
# Enter: user@192.168.1.100
```

This requires SSH server on iPC400 (native in Linux, optional in Windows).

## Testing the Share

Once set up, you can:

1. **Edit files on your laptop**:
   - Open Z:\ (or mapped drive) in VS Code
   - Edit any TIM service file
   - Changes are live on iPC400

2. **Test from iPC400**:
   - Files update immediately
   - Run `git diff` to see your changes
   - Commit and push from either machine

## Troubleshooting

- **"Access Denied"**: Check iPC400 share permissions, ensure user account is correct
- **"Network path not found"**: Verify iPC400 IP is reachable (ping 192.168.1.100)
- **"Timeout"**: Network is slow; try hardwired Ethernet instead of WiFi
- **iPC400 hostname not recognized**: Use IP address instead (192.168.1.100)
