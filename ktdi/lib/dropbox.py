"""Read one folder of a Dropbox (the RPG rulebooks) through Dropbox's API: list it, search it, and make download
links. No Discord code.

The bot uses a Dropbox app with read-only scopes and a refresh token (see README: RPG rulebooks), and never looks
outside the folder it's given. Downloads are Dropbox's own temporary links (valid for 4 hours), so files of any
size work: rulebooks are often far bigger than Discord's upload limit.
"""

import time
from dataclasses import dataclass

import aiohttp

API = "https://api.dropboxapi.com/2/"
TOKEN_URL = "https://api.dropbox.com/oauth2/token"
LISTING_CACHE_SECONDS = 10 * 60  # Re-read the folder at most this often.
LINK_HOURS = 4  # How long Dropbox's temporary links last.


class DropboxError(Exception):
    """A problem talking to Dropbox. The message is safe to show the user who asked.

    private=True means the message names a file, so it mustn't be logged.
    """

    def __init__(self, message: str, private: bool = False):
        super().__init__(message)
        self.private = private

    @property
    def log_text(self) -> str:
        return "(details not logged)" if self.private else str(self)


@dataclass
class RpgFile:
    id: str  # Dropbox's file ID, "id:..."
    path: str  # Inside the folder, e.g. "D&D 5e/Player's Handbook.pdf"
    size: int

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def folder(self) -> str:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""


class Dropbox:
    def __init__(self, app_key: str, app_secret: str, refresh_token: str, root: str, *, api: str = API,
                 token_url: str = TOKEN_URL):
        self.app_key, self.app_secret, self.refresh_token = app_key, app_secret, refresh_token
        self.root = "/" + root.strip("/") if root.strip("/") else ""  # Dropbox's root is "", not "/".
        self.api, self.token_url = api, token_url
        self._access_token: str | None = None
        self._token_expires = 0.0
        self._listing: list[RpgFile] | None = None
        self._listed_at = 0.0
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def _token(self, session: aiohttp.ClientSession, force: bool = False) -> str:
        """A short-lived access token, swapped for the long-lived refresh token whenever it runs out."""
        if self._access_token and not force and time.monotonic() < self._token_expires:
            return self._access_token
        data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token,
                "client_id": self.app_key, "client_secret": self.app_secret}
        async with session.post(self.token_url, data=data) as response:
            if response.status in (400, 401):
                raise DropboxError("Dropbox rejected the bot's login. The DROPBOX_* settings need redoing "
                                   "(see the README).")
            if response.status != 200:
                raise DropboxError(f"Dropbox's login returned an error ({response.status}).")
            body = await response.json(content_type=None)
        self._access_token = body["access_token"]
        self._token_expires = time.monotonic() + int(body.get("expires_in", 14400)) - 60
        return self._access_token

    async def _call(self, session: aiohttp.ClientSession, endpoint: str, payload: dict) -> dict:
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {await self._token(session, force=attempt > 0)}"}
            async with session.post(self.api + endpoint, json=payload, headers=headers) as response:
                if response.status == 401 and attempt == 0:
                    continue  # The token ran out early: get a fresh one and try again.
                if response.status == 409:
                    summary = (await response.json(content_type=None)).get("error_summary", "")
                    if "not_found" in summary:
                        raise DropboxError("Dropbox says that isn't there any more.", private=True)
                    raise DropboxError(f"Dropbox couldn't do that ({summary.split('/')[0] or 'error'}).")
                if response.status in (401, 403):
                    raise DropboxError("Dropbox won't let the bot in. Check the app's permissions (files.metadata.read "
                                       "and files.content.read) and the DROPBOX_* settings.")
                if response.status != 200:
                    raise DropboxError(f"Dropbox returned an error ({response.status}).")
                return await response.json(content_type=None)
        raise DropboxError("Dropbox won't let the bot in.")

    def _session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(timeout=self.timeout)

    async def files(self) -> list[RpgFile]:
        """Every file in the folder (and folders inside it), sorted by path. Cached for a few minutes."""
        if self._listing is not None and time.monotonic() - self._listed_at < LISTING_CACHE_SECONDS:
            return self._listing
        found: list[RpgFile] = []
        try:
            async with self._session() as session:
                try:
                    page = await self._call(session, "files/list_folder",
                                            {"path": self.root, "recursive": True, "limit": 2000})
                except DropboxError as error:
                    if error.private:  # not_found, for the folder itself
                        raise DropboxError(f"Dropbox has no folder `{self.root or '/'}`. Check RPG_DROPBOX_PATH.") from error
                    raise
                while True:
                    for entry in page.get("entries", []):
                        if entry.get(".tag") == "file" and entry.get("is_downloadable", True):
                            path = entry["path_display"][len(self.root):].lstrip("/")
                            found.append(RpgFile(entry["id"], path, int(entry.get("size", 0))))
                    if not page.get("has_more"):
                        break
                    page = await self._call(session, "files/list_folder/continue", {"cursor": page["cursor"]})
        except aiohttp.ClientError as error:
            raise DropboxError(f"Couldn't reach Dropbox ({type(error).__name__}).") from error
        self._listing = sorted(found, key=lambda f: f.path.casefold())
        self._listed_at = time.monotonic()
        return self._listing

    async def search(self, query: str) -> list[RpgFile]:
        """Files whose folder and name contain every word searched for, in any order: "5e player" finds
        "D&D 5e/Player's Handbook.pdf"."""
        words = query.casefold().split()
        return [f for f in await self.files() if all(word in f.path.casefold() for word in words)]

    async def link(self, file: RpgFile) -> str:
        """A temporary download link (Dropbox's, valid for LINK_HOURS). Only within the folder."""
        try:
            async with self._session() as session:
                body = await self._call(session, "files/get_temporary_link", {"path": file.id})
        except aiohttp.ClientError as error:
            raise DropboxError(f"Couldn't reach Dropbox ({type(error).__name__}).") from error
        return body["link"]
