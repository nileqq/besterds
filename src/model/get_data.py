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
        if params is None:
            params = {}

        url = f"{self.BASE_URL}/{method}"

        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()

        data = response.json()

        if data.get("status") != "OK":
            raise RuntimeError(data.get("comment", "Codeforces API Eror"))
        
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
    
    def get_contest_list(self):
        """
        Returns json-file of contests that user participated in + rating change.

        Parameters:
          - head: returns top-K contests list
          - tail: returns bottom-K contests list
          - indent: returns json file beautifully. Initially, None
        """

        return self._get("user.rating", {
            "handle": self.handle
        })
    
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
    
    def get_skipped_count(self):
        """
        Returns skipped contests (where all submissions are skipped)
        """

        contests = self.get_contest_list()
        skipped_contests = 0
        for contest in contests:
            submissions = self.get_contest_submissions(contest["contestId"])

            contest_submissions = [
                s for s in submissions
                if s.get("author", {}).get("participantType") == "CONTESTANT"
            ]

            if not contest_submissions:
                continue

            if all(s.get("verdict") == "SKIPPED" for s in contest_submissions):
                skipped_contests += 1
        
        return skipped_contests