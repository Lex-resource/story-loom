class ThinkStreamParser:
    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self):
        self.in_think = False
        self.buffer = ""

    @staticmethod
    def _trailing_partial_tag_len(buffer: str, tag: str) -> int:
        max_overlap = min(len(buffer), len(tag) - 1)
        for index in range(max_overlap, 0, -1):
            if buffer[-index:] == tag[:index]:
                return index
        return 0

    def process(self, chunk: str) -> tuple[str, str]:
        if not chunk:
            return "", ""
        self.buffer += chunk
        normal = ""
        reasoning = ""
        while self.buffer:
            if not self.in_think:
                idx = self.buffer.find(self.OPEN_TAG)
                if idx != -1:
                    normal += self.buffer[:idx]
                    self.in_think = True
                    self.buffer = self.buffer[idx + len(self.OPEN_TAG):]
                else:
                    partial_len = self._trailing_partial_tag_len(self.buffer, self.OPEN_TAG)
                    if partial_len:
                        normal += self.buffer[:-partial_len]
                        self.buffer = self.buffer[-partial_len:]
                        break
                    normal += self.buffer
                    self.buffer = ""
            else:
                idx = self.buffer.find(self.CLOSE_TAG)
                if idx != -1:
                    reasoning += self.buffer[:idx]
                    self.in_think = False
                    self.buffer = self.buffer[idx + len(self.CLOSE_TAG):]
                else:
                    partial_len = self._trailing_partial_tag_len(self.buffer, self.CLOSE_TAG)
                    if partial_len:
                        reasoning += self.buffer[:-partial_len]
                        self.buffer = self.buffer[-partial_len:]
                        break
                    reasoning += self.buffer
                    self.buffer = ""
        return normal, reasoning

    def flush(self) -> tuple[str, str]:
        normal = ""
        reasoning = ""
        if not self.in_think:
            normal = self.buffer
        else:
            reasoning = self.buffer
        self.buffer = ""
        return normal, reasoning
