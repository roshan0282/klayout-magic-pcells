import json
import unittest

from tests.unit._util import REPO  # noqa: F401
from klayout_magic_pcells import protocol
from klayout_magic_pcells.protocol import ProtocolError, ReplyParser, encode_request, tcl_word


def hx(s):
    return s.encode("utf-8").hex()


class Requests(unittest.TestCase):
    def test_request_is_one_line_of_hex_json(self):
        line = encode_request(7, {"op": "generate", "params": {"w": "x{y", "l": "0.5\n"}})
        self.assertTrue(line.endswith("\n"))
        self.assertEqual(line.count("\n"), 1)
        head, rid, payload = line.strip().split(" ")
        self.assertEqual((head, rid), ("kmp::req", "7"))
        self.assertTrue(all(c in "0123456789abcdef" for c in payload))
        obj = json.loads(bytes.fromhex(payload).decode("utf-8"))
        self.assertEqual(obj["params"]["w"], "x{y")
        # No Tcl-special character can reach the command line itself.
        for ch in "{}[]$\\\"":
            self.assertNotIn(ch, line)

    def test_tcl_word(self):
        self.assertEqual(tcl_word("/a b/{c}$d"), "/a\\ b/\\{c\\}\\$d")


class Replies(unittest.TestCase):
    def feed_all(self, lines):
        p = ReplyParser()
        out = []
        for ln in lines:
            out.append(p.feed(ln))
        return out

    def test_full_reply(self):
        res = self.feed_all([
            "Loading sky130A Device Generator Menu ...",
            "KMP_READY 1",
            "KMP_BEGIN 3",
            "KMP_KV 3 rc " + hx("0"),
            "KMP_KV 3 log ",
            "KMP_KV 3 cell " + hx("sky130_fd_pr__nfet_01v8_8KDQ7Y"),
            "Creating new cell",
            "KMP_PARAM 3 %s %s" % (hx("w"), hx("1.5")),
            "KMP_PARAM 3 %s %s" % (hx("compatible"), hx("a b {c}")),
            "KMP_END 3",
        ])
        self.assertEqual(res[0], ("other", "Loading sky130A Device Generator Menu ..."))
        self.assertEqual(res[1], ("ready", "1"))
        kind, rep = res[-1]
        self.assertEqual(kind, "reply")
        self.assertTrue(rep.ok)
        self.assertEqual(rep.log, "")
        self.assertEqual(rep.kv["cell"], "sky130_fd_pr__nfet_01v8_8KDQ7Y")
        self.assertEqual(list(rep.params), ["w", "compatible"])
        self.assertEqual(rep.params["compatible"], "a b {c}")

    def test_error_reply(self):
        kind, rep = self.feed_all(["KMP_BEGIN 1", "KMP_KV 1 rc " + hx("1"),
                                   "KMP_KV 1 error " + hx("unknown device"), "KMP_END 1"])[-1]
        self.assertFalse(rep.ok)
        self.assertEqual(rep.error, "unknown device")

    def test_framing_errors(self):
        p = ReplyParser()
        with self.assertRaises(ProtocolError):
            p.feed("KMP_KV 9 rc 30")  # no KMP_BEGIN
        p.feed("KMP_BEGIN 2")
        with self.assertRaises(ProtocolError):
            p.feed("KMP_KV 2 rc zz")  # not hex
        with self.assertRaises(ProtocolError):
            p.feed("KMP_BEGIN x")
        with self.assertRaises(ProtocolError):
            p.feed("KMP_WHAT 2")

    def test_protocol_version(self):
        self.assertEqual(protocol.PROTOCOL, 1)


if __name__ == "__main__":
    unittest.main()
