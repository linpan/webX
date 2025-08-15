import enum

from pydantic import BaseModel

from typing_extensions import TypedDict


# searchRequest
class SearchParams(TypedDict):
    q: str
    format: str
    lang: str
    safesearch: str
    engines: str


class SearchMode(enum.Enum):
    """
    Search Context Size Thresholds
    """

    low = "low"  # snippets
    medium = "medium"  # content threshold 1000
    high = "high"  # content threshold 3000
    ultra = "ultra"  # content threshold 5000

    @property
    def context_size(self) -> int:
        match self:
            case SearchMode.low:
                return 1000
            case SearchMode.medium:
                return 2000
            case SearchMode.high:
                return 3000
            case SearchMode.ultra:
                return 5000
            case _:
                return 1000

        return 1000


class SearchSnippets(TypedDict, total=False):
    url: str | None
    title: str | None
    content: str | None
    score: float | None


class SearchResponse(BaseModel):
    """
    Search Response Model
    """

    q: str
    mode: SearchMode
    snippets: list[SearchSnippets] | None = None
    time: str | None = None


if __name__ == "__main__":
    s = SearchMode.high
    print(s.context_size)
