# 1Password Access Auditor

This tool generates a CSV report of all users, the vaults they have access to, and their specific permissions within those vaults.

## Prerequisites

1.  **1Password CLI (`op`)**: You must have the 1Password CLI installed.
    *   [Installation Guide](https://developer.1password.com/docs/cli/get-started/)
2.  **Python 3**: The script requires Python 3 to run.

## Setup

1.  Ensure you are signed in to your 1Password account via the CLI:
    ```bash
    op signin
    ```

## Usage

Run the script using Python:

```bash
python3 1password_audit.py
```

The script will generate a file named `1password_access_report.csv` in the same directory.

## Output Format

The CSV file contains the following columns:
*   **User Name**: The display name of the user.
*   **User Email**: The email address of the user.
*   **Vault Name**: The name of the vault the user has access to.
*   **Permissions**: A comma-separated list of permissions the user has in that vault (e.g., `allow_viewing`, `allow_editing`).
*   **Access Via**: Indicates how the user has access: "Direct" and/or "Group: [Group Name]".
