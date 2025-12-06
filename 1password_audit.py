import subprocess
import json
import csv
import sys
import shutil
import time
import os
import asyncio
from typing import List, Dict, Any

def check_op_installed():
    """Checks if the 'op' CLI is installed."""
    if not shutil.which("op"):
        print("❌ Error: 'op' CLI is not installed or not in PATH.")
        print("   Please install the 1Password CLI: https://developer.1password.com/docs/cli/get-started/")
        sys.exit(1)

def check_op_signin():
    """Checks if the user is signed in to 'op'."""
    try:
        # 'op whoami' returns 0 if signed in, non-zero otherwise
        subprocess.run(["op", "whoami"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("❌ Error: You are not signed in to 1Password CLI.")
        print("   Please run 'op signin' first.")
        sys.exit(1)

async def run_subprocess(cmd: List[str], capture_output: bool = True, text: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """Async wrapper for subprocess.run."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE if capture_output else None,
        stderr=asyncio.subprocess.PIPE if capture_output else None
    )
    stdout, stderr = await process.communicate()
    return subprocess.CompletedProcess(cmd, process.returncode, stdout.decode() if text and stdout else stdout,
                                       stderr.decode() if text and stderr else stderr)

async def get_vaults() -> List[Dict[str, Any]]:
    """Fetches a list of all vaults the user can manage."""
    try:
        result = await run_subprocess(["op", "vault", "list", "--permission", "manage_vault", "--format=json"])
        result.check_returncode()
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"❌ Error fetching vaults: {e}")
        sys.exit(1)

async def get_all_groups() -> List[Dict[str, Any]]:
    """Fetches a list of all groups."""
    try:
        result = await run_subprocess(["op", "group", "list", "--format=json"])
        result.check_returncode()
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"❌ Error fetching groups: {e}")
        sys.exit(1)

async def get_vault_users(vault_id: str) -> List[Dict[str, Any]]:
    """Fetches users with access to a specific vault."""
    try:
        result = await run_subprocess(["op", "vault", "user", "list", vault_id, "--format=json"])
        result.check_returncode()
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        # Some vaults might not allow listing users or might be empty/special
        return []

async def get_vault_groups(vault_id: str) -> List[Dict[str, Any]]:
    """Fetches groups with access to a specific vault."""
    try:
        result = await run_subprocess(["op", "vault", "group", "list", vault_id, "--format=json"])
        result.check_returncode()
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []

async def get_group_members(group_id: str) -> List[Dict[str, Any]]:
    """Fetches members of a specific group."""
    try:
        result = await run_subprocess(["op", "group", "user", "list", group_id, "--format=json"])
        result.check_returncode()
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []

async def fetch_group_members(group_id: str) -> tuple[str, List[Dict[str, Any]]]:
    """Wrapper for fetching group members."""
    members = await get_group_members(group_id)
    return group_id, members

async def print_progress(current: int, total: int, prefix: str = "Progress", icon: str = "⚡"):
    """Simple progress bar."""
    if total == 0:
        return
    percent = (current / total) * 100
    bar_length = 20
    filled_length = int(bar_length * current // total)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    print(f'\r{icon} {prefix}: |{bar}| {current}/{total} ({percent:.0f}%)', end='', flush=True)
    if current == total:
        print()

async def process_vault(vault: Dict[str, Any], group_members_cache: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Processes a single vault, fetching direct users and group-based access."""
    vault_name = vault.get("name", "Unknown Vault")
    vault_id = vault.get("id")

    if not vault_id:
        return []

    # Dictionary to track user access for this vault
    # Key: user_id, Value: {name, email, permissions, access_via (set)}
    vault_access: Dict[str, Dict[str, Any]] = {}

    # 1. Get Direct Access
    direct_users = await get_vault_users(vault_id)
    for user in direct_users:
        user_id = user.get("id")
        if not user_id: continue

        if user_id not in vault_access:
            vault_access[user_id] = {
                "name": user.get("name", "Unknown User"),
                "email": user.get("email", "No Email"),
                "permissions": set(user.get("permissions", [])),
                "access_via": set(["Direct"])
            }
        else:
            vault_access[user_id]["access_via"].add("Direct")
            vault_access[user_id]["permissions"].update(user.get("permissions", []))

    # 2. Get Group Access (using cached members)
    groups = await get_vault_groups(vault_id)
    for group in groups:
        group_name = group.get("name", "Unknown Group")
        group_id = group.get("id")
        group_permissions = group.get("permissions", [])

        if not group_id: continue

        group_members = group_members_cache.get(group_id, [])
        for member in group_members:
            user_id = member.get("id")
            if not user_id: continue

            if user_id not in vault_access:
                vault_access[user_id] = {
                    "name": member.get("name", "Unknown User"),
                    "email": member.get("email", "No Email"),
                    "permissions": set(group_permissions),
                    "access_via": set([f"Group: {group_name}"])
                }
            else:
                vault_access[user_id]["access_via"].add(f"Group: {group_name}")
                vault_access[user_id]["permissions"].update(group_permissions)

    # 3. Flatten for Report
    local_report = []
    for user_data in vault_access.values():
        permissions_str = ", ".join(sorted(list(user_data["permissions"])))
        access_via_str = ", ".join(sorted(list(user_data["access_via"])))

        local_report.append({
            "User Name": user_data["name"],
            "User Email": user_data["email"],
            "Vault Name": vault_name,
            "Permissions": permissions_str,
            "Access Via": access_via_str
        })

    return local_report

async def main():
    print("🔍 1Password Access Audit Starting...\n")
    
    print("   Stage 1: Verifying CLI setup")
    check_op_installed()
    check_op_signin()
    print("      ✅ CLI ready\n")

    print("   Stage 2: Fetching vaults")
    vaults = await get_vaults()
    print(f"      📂 {len(vaults)} vaults found\n")

    print("   Stage 3: Fetching groups")
    all_groups = await get_all_groups()
    relevant_groups = [g for g in all_groups if g.get("id")]
    total_groups = len(relevant_groups)
    print(f"      👥 {len(all_groups)} groups total ({total_groups} relevant)\n")

    print("   Stage 4: Loading group members")
    group_members_cache: Dict[str, List[Dict[str, Any]]] = {}
    if total_groups > 0:
        tasks = [fetch_group_members(g["id"]) for g in relevant_groups]
        completed = 0
        for coro in asyncio.as_completed(tasks):
            group_id, members = await coro
            group_members_cache[group_id] = members
            completed += 1
            await print_progress(completed, total_groups, "Loading", "👥")
        print("      ✅ Groups loaded\n")
    else:
        print("      ℹ️  No groups to load\n")

    print("   Stage 5: Auditing vault access")
    report_data: List[Dict[str, Any]] = []
    total_vaults = len(vaults)
    if total_vaults > 0:
        tasks = [process_vault(vault, group_members_cache) for vault in vaults]
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            report_data.extend(result)
            completed += 1
            await print_progress(completed, total_vaults, "Auditing", "📂")
        print("      ✅ Audit complete\n")
    else:
        print("      ℹ️  No vaults to audit\n")

    print("   Stage 6: Generating report")
    output_file = "1password_access_report.csv"
    fieldnames = ["User Name", "User Email", "Vault Name", "Permissions", "Access Via"]

    try:
        with open(output_file, mode="w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in report_data:
                writer.writerow(row)
        full_path = os.path.abspath(output_file)
        print(f"      📊 Report saved: {full_path} ({len(report_data)} entries)\n")
    except IOError as e:
        print(f"      ❌ Error writing to file {output_file}: {e}\n")

    print("🎉 Audit finished successfully!")
    print()

if __name__ == "__main__":
    asyncio.run(main())