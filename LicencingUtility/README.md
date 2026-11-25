# cLicencingUtility

Vendor-side utility and procedure for creating and signing `license.lic` files.
Do not include this folder or the vendor private key in a client installation.

## Important files and key safety

- `license_tool.py` generates the signing keypair and issues licenses.
- `vendor_private_key.pem` is kept at the project root and is used only by the
  issuer. Keep it secret, back it up securely, and never send it to a client.
- The application's public key is `VENDOR_PUBLIC_KEY_B64` in
  `app/services/license.py`. The public key is safe to distribute with the app.
- The private key is ignored by Git. Keep a secure backup of the existing key;
  losing it means you cannot issue licenses accepted by apps using its public
  key.

The application package builder copies the app and selected installer files,
not this vendor utility folder. Do not manually add this utility or the private
key to a client package.

## One-time signing key setup

The repository already has a signing key. **Do not run `genkeypair` for routine
license issuance.** The command refuses to overwrite an existing key.

Only when establishing a brand-new signing keypair:

1. From the repository root, run:

   ```powershell
   .\.venv\Scripts\python.exe cLicencingUtility\license_tool.py genkeypair
   ```

2. Back up `vendor_private_key.pem` securely. Never commit or distribute it.
3. Copy the printed public key into `VENDOR_PUBLIC_KEY_B64` in
   `app/services/license.py`.
4. Rebuild and deploy the app with that public key before issuing licenses.

Changing the signing key requires a matching public key in the app. Existing
licenses signed by a different private key will not verify against the new
public key.

## Issue a license for a client

### 1. Collect the target computer's machine ID

On the Windows computer where the application will be installed, run this from
the application installation folder:

```powershell
.\.venv\Scripts\python.exe -m app.services.license
```

The client sends you the displayed **Machine ID**. Use it exactly as printed;
the license is bound to that computer. Also obtain the lab/client name and
agree on an optional expiry date.

### 2. Create an output folder

On the vendor/issuer computer, create a secure folder for issued license files.
The folder must exist before using it as `--out`:

```powershell
New-Item -ItemType Directory -Path "C:\SecureLicenses" -Force
```

### 3. Sign and write the license

From the repository root, run the command below, replacing the example machine
ID, lab name, and date with the client's details:

```powershell
.\.venv\Scripts\python.exe cLicencingUtility\license_tool.py issue `
  --machine-id "AB12-CD34-EF56-7890" `
  --licensed-to "Client Lab Name" `
  --expires "2027-08-30" `
  --out "C:\SecureLicenses\license.lic"
```

`--expires` is optional. Omit that entire line for a license with no expiry.
Expiry is a calendar date (`YYYY-MM-DD`), not a time. The application considers
the license valid through the expiry date.

The utility writes the signed JSON to `C:\SecureLicenses\license.lic` and also
prints it to the terminal. The `--out` value must be a **file path**, not just a
directory.

### 4. Deliver and install the license

Send only `license.lic` to the client. The client copies it into the
application installation folder, next to `service_installer.py`, then restarts
the service from an elevated PowerShell window:

```powershell
.\manage_service.ps1 restart
```

Never send `vendor_private_key.pem`. A separate license must be issued for each
target machine.

## Troubleshooting

- **`No signing key`**: restore the existing `vendor_private_key.pem` from its
  secure backup. Do not generate a replacement unless you intend to rotate the
  public key in the app and redeploy it.
- **`FileNotFoundError` while writing the license**: create the parent folder
  for the `--out` path, or choose an existing folder.
- **License rejected as wrong-machine**: confirm the `machine_id` came from the
  exact computer running the service and was copied without alteration.
- **Invalid signature**: confirm the deployed app embeds the public key that
  matches the private key used by this utility, and that the license file was
  not edited after issuance.
