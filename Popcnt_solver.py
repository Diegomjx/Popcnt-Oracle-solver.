#!/usr/bin/env python3
"""
Popcnt Oracle solver.

Idea:
  query x_k = c * 2^(e*k) mod n   ->  w_k  = popcount(v_k),  v_k = m*2^k mod n
  query x'_k = n - x_k            ->  w'_k = popcount(-v_k mod n)

  v_{k+1} = 2*v_k - b*n where b = (k+1)-th bit of alpha = m/n.
    b=0  -> v doubles exactly  -> w flat (guaranteed); w' jumps (usually)
    b=1  -> v wraps           -> w jumps (usually);     w' flat (guaranteed)
  So: w jump => bit 1, w' jump => bit 0, both flat => ambiguous (~1.1%).
  Ambiguous bits are resolved offline: m = (A*n) >> K where A is the bit
  string; each ambiguous bit p contributes a known d_p = 2^(K-p)*n.
  Gray-code enumerate subsets, filter with popcount(m) == w_0 etc.,
  verify with pow(m, e, n) == c.
"""
import socket, re, threading, time, sys

HOST = "tcp.flagyard.com"
PORT = 30754

K = 2064                    # decode bits 1..K of alpha = m/n
COLLECT_TIMEOUT = 30 * 60   # max seconds for query collection
SEARCH_TIME_BUDGET = 8 * 60   # if expected search exceeds this, retry connection
KEEPALIVE_INTERVAL = 25
FAILDUMP = "/home/user/popcnt/faildump_%d.json"


def log(msg):
    print("[%7.1fs] %s" % (time.time() - T0, msg), flush=True)


class Retry(Exception):
    pass


def attempt(host, port):
    s = socket.create_connection((host, port), timeout=90)
    s.settimeout(None)

    # ---------- banner ----------
    buf = bytearray()
    while b"x> " not in buf:
        ch = s.recv(65536)
        if not ch:
            raise Retry("closed during banner")
        buf += ch
    banner = buf.decode(errors="replace")
    e = int(re.search(r"e = (\d+)", banner).group(1))
    n = int(re.search(r"n = (\d+)", banner).group(1))
    c = int(re.search(r"c = (\d+)", banner).group(1))
    L = n.bit_length()
    log("got params: e=%d n(%d bits) c(%d bits)" % (e, L, c.bit_length()))

    # ---------- build all queries (non-adaptive) ----------
    two_e = pow(2, e, n)
    xs = []
    x = c % n
    cur = 1
    xs.append(x)
    for k in range(1, K + 1):
        cur = cur * two_e % n
        xs.append(c * cur % n)
    xs2 = [(n - v) % n for v in xs]
    qs = xs + xs2                      # chain w first, then chain w'
    payload = ("\n".join(map(str, qs)) + "\n").encode()
    log("sending %d queries (%.1f MB)..." % (len(qs), len(payload) / 1e6))

    recv_buf = bytearray()
    dead = [False]

    def reader():
        try:
            while True:
                ch = s.recv(65536)
                if not ch:
                    break
                recv_buf.extend(ch)
        except Exception:
            pass
        dead[0] = True

    threading.Thread(target=reader, daemon=True).start()
    s.sendall(payload)
    log("payload sent; waiting for responses...")

    need = len(qs)
    t0 = time.time()
    nvals = 0
    # response stream = "N1\nx> N2\nx> N3\n..." (first prompt came with banner)
    while True:
        data = bytes(recv_buf)
        nvals = len(re.findall(rb"\d+", data))
        if nvals >= need and not data[-1:].isdigit():
            break
        if dead[0]:
            raise Retry("connection died during collection (got %d/%d)" % (nvals, need))
        if time.time() - t0 > COLLECT_TIMEOUT:
            raise Retry("collection timeout (%d/%d)" % (nvals, need))
        time.sleep(3)
        if int(time.time() - t0) % 60 < 3:
            log("collected %d/%d responses..." % (nvals, need))
    vals = re.findall(rb"\d+", bytes(recv_buf))[:need]
    nums = [int(v) for v in vals]
    w = nums[:K + 1]
    wp = nums[K + 1:]
    log("all %d responses collected" % need)

    # ---------- decode ----------
    bits = [None] * (K + 2)
    P = []
    for i in range(1, K + 1):
        j1 = w[i - 1] != w[i]
        j2 = wp[i - 1] != wp[i]
        if j1 and j2:
            import json
            with open(FAILDUMP % int(time.time()), "w") as fh:
                json.dump({"e": e, "n": n, "c": c, "w": w, "wp": wp,
                           "contra": i}, fh)
            raise Retry("decode contradiction at %d (data corrupt?)" % i)
        if j1:
            bits[i] = 1
        elif j2:
            bits[i] = 0
        else:
            P.append(i)
    r = len(P)
    log("decoded: %d ambiguous positions (%.2f%%): %s" % (r, 100.0 * r / K, P[:40]))
    if r > 40:
        raise Retry("too many ambiguities (%d)" % r)
    est = (1 << r) * 1.4e-6
    log("search space 2^%d, est %.0fs" % (r, est))
    if est > SEARCH_TIME_BUDGET:
        raise Retry("search too big (2^%d)" % r)

    # ---------- keep-alive during search ----------
    stop = threading.Event()

    def keepalive():
        while not stop.wait(KEEPALIVE_INTERVAL):
            try:
                s.sendall(b"1\n")
            except Exception:
                return

    threading.Thread(target=keepalive, daemon=True).start()

    # ---------- flat Gray-code subset search ----------
    A = 0
    for i in range(1, K + 1):
        A = (A << 1) | (bits[i] or 0)
    Pbase = A * n
    ds = [(1 << (K - p)) * n for p in P]
    w0 = w[0]
    # second-stage filters
    fk = [97, 311, 509, 1013]
    fp = [pow(2, k, n) for k in fk]
    fw = [w[k] for k in fk]

    def survivor(m_c):
        for j in range(len(fk)):
            if (m_c * fp[j] % n).bit_count() != fw[j]:
                return False
        return True

    found = None
    checked = 0

    def try_X(X):
        nonlocal found
        for m_c in (X, X + 1):
            if m_c.bit_count() != w0:
                continue
            if not survivor(m_c):
                continue
            if pow(m_c, e, n) == c:
                found = m_c
                return True
        return False

    sel = [False] * r
    curp = Pbase
    total = 1 << r
    t1 = time.time()
    for i in range(total):
        if i:
            t = (i & -i).bit_length() - 1
            if sel[t]:
                curp -= ds[t]
                sel[t] = False
            else:
                curp += ds[t]
                sel[t] = True
        X = curp >> K
        pcx = X.bit_count()
        if pcx == w0:
            checked += 1
            if try_X(X):
                break
        elif pcx >= w0 - 1 and ((pcx - w0) & 1) == 1 and (X + 1).bit_count() == w0:
            checked += 1
            if try_X(X):
                break
        if (i & 0xFFFFFF) == 0 and i:
            log("search %d/%d (%.0fs elapsed, %d survivors-tested)" %
                (i, total, time.time() - t1, checked))
    stop.set()
    log("search done in %.0fs (survivors tested: %d)" % (time.time() - t1, checked))
    if found is None:
        import json
        with open(FAILDUMP % int(time.time()), "w") as fh:
            json.dump({"e": e, "n": n, "c": c, "w": w, "wp": wp,
                       "P": P, "r": r, "checked": checked}, fh)
        log("state dumped for offline analysis")
        raise Retry("no candidate verified")

    # ---------- final exchange ----------
    log("m recovered (%d bits) -- verified m^e == c" % found.bit_length())
    s.sendall(str(found).encode() + b"\n")
    deadline = time.time() + 90
    flag = None
    while time.time() < deadline:
        data = bytes(recv_buf)
        for line in data.split(b"\n"):
            ls = line.strip()
            if not ls:
                continue
            ls2 = re.sub(rb"^x> ?", b"", ls)
            if not ls2 or re.fullmatch(rb"\d+", ls2):
                continue
            flag = ls2.decode(errors="replace")
            break
        if flag:
            break
        if dead[0]:
            break
        time.sleep(1)
    # wait a bit for EOF to grab everything
    time.sleep(2)
    data = bytes(recv_buf)
    tail = data[-400:]
    try:
        s.close()
    except Exception:
        pass
    return flag, tail


if __name__ == "__main__":
    T0 = time.time()
    host = HOST
    port = PORT
    if len(sys.argv) >= 3:
        host, port = sys.argv[1], int(sys.argv[2])
    tries = 0
    while True:
        tries += 1
        try:
            flag, tail = attempt(host, port)
            if flag:
                print("\n*** FLAG: %s ***\n" % flag)
                break
            else:
                print("\nno flag line found; tail=%r" % tail)
                break
        except Retry as ex:
            log("attempt %d failed: %s" % (tries, ex))
            if tries >= 5:
                print("giving up")
                break
            log("retrying with a fresh connection...")
            time.sleep(2)
        except Exception as ex:
            log("attempt %d error: %r" % (tries, ex))
            if tries >= 5:
                print("giving up")
                break
            log("retrying with a fresh connection...")
            time.sleep(2)
