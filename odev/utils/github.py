from contextlib import nullcontext
from typing import Optional, ContextManager

from github import Github

from .utils import password
from .secrets import secret_storage, StoreSecret


__all__ = ["get_github"]


def get_github(token: Optional[str] = None) -> Github:
    save: bool = False
    storage_context: ContextManager[Optional[str]] = nullcontext(token)
    if token is None:
        storage_context = secret_storage("github_token")
    try:
        with storage_context as token:
            if token is None:
                token = password("Github token:")
                save = True
            github: Github = Github(token)
            _ = github.get_user().login  # will raise with bad credentials
            if save:  # save only after we've verified validity
                raise StoreSecret(token)
    finally:
        pass
    return github
