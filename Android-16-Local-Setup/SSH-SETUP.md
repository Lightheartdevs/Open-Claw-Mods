# SSH Key-Based Auth Setup (.143 → .122)

**Completed:** 2026-02-13
**Purpose:** Allow OpenClaw agent on .143 to SSH to .122 without password prompts

## What Was Done

The OpenClaw agent uses the `exec` tool to run shell commands. When the agent tries `ssh michael@192.168.0.122`, SSH prompts for a password interactively — but the agent can't provide interactive input, so it hangs forever.

The fix: set up key-based authentication so SSH never asks for a password.

## Setup Steps

### 1. Generated ED25519 key on .143
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N '' -C 'android-16@tower2'
```

Key fingerprint: `SHA256:Fd/67LKf3snj4FMnb2BtNz07TS077U7uyV3MreamT+4`
Public key: `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPoNSurTyWzlS4RyWQTQOzLy/hxcni6G4wohrShV8j3c android-16@tower2`

### 2. Copied public key to .122's authorized_keys
```bash
sudo apt-get install -y sshpass
sshpass -p '##Linux-8488##' ssh-copy-id -o StrictHostKeyChecking=no michael@192.168.0.122
```

### 3. Added SSH config on .143
Added to `~/.ssh/config`:
```
Host 192.168.0.122
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    User michael
```

The `StrictHostKeyChecking no` and `/dev/null` known_hosts prevent the "are you sure you want to connect?" prompt that would also hang the agent.

## Verification

```bash
# This should work without any prompts:
ssh -o BatchMode=yes michael@192.168.0.122 'echo OK && hostname'
# Expected: OK \n lightheartworker
```

## Full SSH Config on .143

```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/android-collective
  IdentitiesOnly yes

Host github-collective
    HostName github.com
    User git
    IdentityFile ~/.ssh/android-collective
    IdentitiesOnly yes

Host 192.168.0.122
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    User michael
```

## Security Notes

- The key has no passphrase (required for non-interactive agent use)
- `StrictHostKeyChecking no` means SSH won't verify the host key — acceptable on a private LAN
- `UserKnownHostsFile /dev/null` prevents "host key changed" warnings if .122 is rebuilt
- The public key is in .122's `~/.ssh/authorized_keys`
