import requests
import json

# Returns raw data (json-files) about user.

class GetData:
    BASE_URL = "https://codeforces.com/api"

    def __init__(self, handle: str):
        """
        Gets username of the user.

        Parameters:
          - handle: field where handle of the user is stored
        """
        self.handle = handle

    
    def _get(self, method: str, params: dict | None = None):
        """
        Wrapper for functions

        Parameters:
           - method: used for request. For example, site.url.com/{method}
           - params: used for method-requests. For example, site.url.com/{method}?{params}
        
        More examples: codeforces.com/user.status?handle=nileq
        Here, user.status = method; handle = params.
        """
        if params is None:
            params = {}

        url = f"{self.BASE_URL}/{method}"

        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()

        data = response.json()

        if data.get("status") != "OK":
            raise RuntimeError(data.get("comment", "Codeforces API Error"))
        
        return data["result"]
    
    def beautify(self, data, indent: int):
        if indent < 0:
            raise ValueError("indent must be >= 0")
        
        return json.dumps(data, indent=indent)

    def get_user_info(self):
        """
        Gets user.info object and returns dict.

        Parameters:
          - indent: returns json-file with indent
        """

        return self._get("user.info", {
            "handles": self.handle 
        })
    
    def get_contest_list(self, head=None, tail=None):
        """
        Returns json-file of contests that user participated in + rating change.

        Parameters:
          - head: returns top-K contests list. In other words, the newest ones.
          - tail: returns bottom-K contests list. In other words, the oldest ones.
          - indent: returns json file beautifully. Initially, None
        """

        if head is not None and head < 0:
            raise ValueError("head must be >= 0")
        
        if tail is not None and tail < 0:
            raise ValueError("tail must be >= 0")
        
        if head is not None and tail is not None:
            raise ValueError("head and tail both can't have values simultaneously")
        
        contests = self._get("user.rating", {
            "handle": self.handle
        })

        if head is not None:
            return contests[:head]
        
        if tail is not None:
            return contests[-tail:]
        
        return contests
    
    def get_contest_submissions(self, contest_id):
        """
        Returns contest submissions of the user.

        Parameters:
          - contest_id: id of the contest. For example, codeforces.com/contests/contest_id.
          It is unique for all contests.
        """

        return self._get("contest.status", {
            "contestId": contest_id,
            "handle": self.handle
        })

    def get_contest_standings(self, contest_id, handles=None, from_=1, count=None, show_unofficial=True):
        """
        Returns contest standings.
        """

        params = {
            "contestId": contest_id,
            "from": from_,
            "showUnofficial": str(show_unofficial).lower(),
        }

        if handles is not None:
            params["handles"] = ";".join(handles)

        if count is not None:
            params["count"] = count

        return self._get("contest.standings", params)
    
    def get_submissions(self, head=None, tail=None):
        """
        Returns submissions of the user.
        
        Parameters:
          - head: returns top-K submissions. In other words, the newest ones.
          - tail: returns bottom-K submissions. In other words, the oldest ones.
        """

        if head is not None and head < 0:
            raise ValueError("head must be >= 0")
        
        if tail is not None and tail < 0:
            raise ValueError("tail must be >= 0")
        
        if head is not None and tail is not None:
            raise ValueError("head and tail both can't have values simultaneously")
        
        submissions = self._get("user.status", {
            "handle": self.handle
        })

        if head is not None:
            return submissions[:head]
        
        if tail is not None:
            return submissions[-tail:]
        
        return submissions
    
    def get_skipped_count(self, until=None, contests=None):
        """
        Returns skipped contests (where all submissions are skipped)
        """

        if contests is None:
            contests = self.get_contest_list(head=until)
        elif until is not None:
            contests = contests[:until]

        rated_contest_ids = {contest["contestId"] for contest in contests}
        submissions_by_contest = {contest_id: [] for contest_id in rated_contest_ids}

        for submission in self.get_submissions():
            contest_id = submission.get("contestId")
            if contest_id not in rated_contest_ids:
                continue

            if submission.get("author", {}).get("participantType") != "CONTESTANT":
                continue

            submissions_by_contest[contest_id].append(submission)

        skipped_contests = 0
        for contest_submissions in submissions_by_contest.values():
            if not contest_submissions:
                continue

            if all(s.get("verdict") == "SKIPPED" for s in contest_submissions):
                skipped_contests += 1
        
        return skipped_contests
