import subprocess
import json
import csv
import sys
import shutil

def check_op_installed():
    """Checks if the 'op' CLI is installed."""
    if not shutil.which("op"):
        print("Error: 'op' CLI is not installed or not in PATH.")
        print("Please install the 1Password CLI: https://developer.1password.com/docs/cli/get-started/")
        sys.exit(1)

def check_op_signin():
    """Checks if the user is signed in to 'op'."""
    try:
        # 'op whoami' returns 0 if signed in, non-zero otherwise
        subprocess.run(["op", "whoami"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("Error: You are not signed in to 1Password CLI.")
        print("Please run 'op signin' first.")
        sys.exit(1)

def get_vaults():
    """Fetches a list of all vaults."""
    try:
        result = subprocess.run(["op", "vault", "list", "--format=json"], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching vaults: {e.stderr}")
        sys.exit(1)

def get_vault_users(vault_id):
    """Fetches users with access to a specific vault."""
    try:
        result = subprocess.run(["op", "vault", "user", "list", vault_id, "--format=json"], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        # Some vaults might not allow listing users or might be empty/special
        print(f"Warning: Could not fetch users for vault ID {vault_id}: {e.stderr.strip()}")
        return []

def get_vault_groups(vault_id):
    """Fetches groups with access to a specific vault."""
    try:
        result = subprocess.run(["op", "vault", "group", "list", vault_id, "--format=json"], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not fetch groups for vault ID {vault_id}: {e.stderr.strip()}")
        return []

def get_group_members(group_id):
    """Fetches members of a specific group."""
    try:
        result = subprocess.run(["op", "group", "user", "list", group_id, "--format=json"], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not fetch members for group ID {group_id}: {e.stderr.strip()}")
        return []

def main():
    print("Checking 1Password CLI status...")
    check_op_installed()
    check_op_signin()

    print("Fetching vaults...")
    vaults = get_vaults()

    report_data = []

    print(f"Found {len(vaults)} vaults. Scanning permissions...")

    for vault in vaults:
        vault_name = vault.get("name", "Unknown Vault")
        vault_id = vault.get("id")

        if not vault_id:
            continue

        # Dictionary to track user access for this vault
        # Key: user_id, Value: {name, email, permissions, access_via (set)}
        vault_access = {}

        # 1. Get Direct Access
        direct_users = get_vault_users(vault_id)
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

        # 2. Get Group Access
        groups = get_vault_groups(vault_id)
        for group in groups:
            group_name = group.get("name", "Unknown Group")
            group_id = group.get("id")
            group_permissions = group.get("permissions", [])

            if not group_id: continue

            group_members = get_group_members(group_id)
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
        for user_data in vault_access.values():
            permissions_str = ", ".join(sorted(list(user_data["permissions"])))
            access_via_str = ", ".join(sorted(list(user_data["access_via"])))

            report_data.append({
                "User Name": user_data["name"],
                "User Email": user_data["email"],
                "Vault Name": vault_name,
                "Permissions": permissions_str,
                "Access Via": access_via_str
            })

    output_file = "1password_access_report.csv"
    print(f"Generating report: {output_file}")

    fieldnames = ["User Name", "User Email", "Vault Name", "Permissions", "Access Via"]

    try:
        with open(output_file, mode="w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in report_data:
                writer.writerow(row)
        print("Done!")
    except IOError as e:
        print(f"Error writing to file {output_file}: {e}")

if __name__ == "__main__":
    main()
