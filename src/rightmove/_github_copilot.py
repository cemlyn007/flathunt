import httpx

COMPLETIONS_URL = "https://api.githubcopilot.com/chat/completions"

_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"


async def get_copilot_token(github_token: str) -> str:
    """Exchange a GitHub personal access token for a short-lived Copilot session token.

    The returned token is valid for approximately 30 minutes and should be used
    as a Bearer token against the Copilot chat completions endpoint.

    Args:
        github_token: A GitHub PAT with Copilot access.

    Returns:
        A short-lived Copilot session token string.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            _TOKEN_URL,
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
    return response.json()["token"]
