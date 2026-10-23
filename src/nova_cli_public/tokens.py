from nova_cli_public.config import Profile
from nova_cli_public.errors import TokenStoreUnavailable

SERVICE_NAME = "nova-cli-public"


class KeyringTokenStore:
    def __init__(self) -> None:
        try:
            import keyring  # type: ignore
        except Exception as exc:
            raise TokenStoreUnavailable("Python keyring package is not available") from exc
        self._keyring = keyring

    def _set_password(self, entry: str, secret: str) -> None:
        try:
            self._keyring.set_password(SERVICE_NAME, entry, secret)
        except Exception:  # noqa: BLE001 - backend exceptions must not expose credentials
            # Backend errors may include secrets; expose only recovery guidance.
            raise TokenStoreUnavailable(
                "Could not save the credential in the OS credential store. "
                "On macOS, unlock your login keychain in Keychain Access and retry "
                "from Terminal in your logged-in desktop session. "
                "The new credential was not saved; repeat authentication after fixing storage."
            ) from None

    def get_refresh_token(self, profile: Profile) -> str | None:
        return self._keyring.get_password(SERVICE_NAME, profile.name)

    def set_refresh_token(self, profile: Profile, refresh_token: str) -> None:
        self._set_password(profile.name, refresh_token)

    def delete_refresh_token_strict(self, profile: Profile) -> None:
        try:
            if self._keyring.get_password(SERVICE_NAME, profile.name) is not None:
                self._keyring.delete_password(SERVICE_NAME, profile.name)
            if self._keyring.get_password(SERVICE_NAME, profile.name) is not None:
                raise ValueError()
        except Exception:  # noqa: BLE001 - keyring exceptions can contain credentials
            raise TokenStoreUnavailable(
                "Could not delete delegated credentials. Unlock the OS credential store."
            ) from None
