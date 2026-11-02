_KIND = {"살충": "insecticide", "살균": "fungicide", "균충": "both"}


def form_of(item_name: str) -> str | None:
    """제형 = 품목명의 마지막 단어 (예: '아미설브롬 입상수화제' → '입상수화제')."""
    _, space, form = item_name.rpartition(" ")
    return form if space else None


def kind_of(usage: str) -> str | None:
    return _KIND.get(usage)
