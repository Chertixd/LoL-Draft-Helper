class InvalidLane(Exception):
    def __init__(self, lane: str):
        super().__init__(f"Invalid lane '{lane}'. See valid lanes with `display_lanes()`.")


class InvalidRank(Exception):
    def __init__(self, rank: str):
        super().__init__(f"Invalid rank '{rank}'. See valid ranks with `display_ranks()`.")
