from re import match, sub

COMPLEX_KEYS = "macie", "ec2-patching", "ssm-patching", "replication-completion-report"


class ObjectKeySanitizer:
    def __call__(self, object_key: str) -> str:
        self.object_key = object_key
        self.complex_keys_handler()
        self.drop_filename()
        self.drop_date()
        self.drop_organization_id()
        self.drop_account_id()
        self.drop_region()
        return self.object_key

    def complex_keys_handler(self) -> None:
        for key in COMPLEX_KEYS:
            if key in self.object_key:
                self.object_key = key

    def drop_filename(self) -> None:
        self.object_key = self.object_key.rsplit("/", maxsplit=1)[0]

    def drop_date(self) -> None:
        if date := match(r"^(.*)(\d{4}/\d{1,2}/\d{1,2}/?\d{,2})(.*)$", self.object_key):
            self.object_key = date.group(1)
            if len(date.groups()) > 2:
                self.object_key += date.group(3)

    def drop_organization_id(self) -> None:
        self.object_key = sub(r"/?o-[a-z0-9]{10,32}/?", "", self.object_key)

    def drop_account_id(self) -> None:
        self.object_key = sub(r"/?-?\d{12}", "", self.object_key)
        if "/accountid=" in self.object_key:
            self.object_key = self.object_key.replace("/accountid=", "")

    def drop_region(self) -> None:
        self.object_key = sub(r"/?-?[a-z]{2}-[a-z]{4,}-\d", "", self.object_key)
        if "/region=" in self.object_key:
            self.object_key = self.object_key.replace("/region=", "")
