"""Regenerate the three Hamiltonian decompositions from a RAW google-nmr coupling matrix,
byte-compatibly with Marika's `hamiltonian_decomposition`.

Needed because the raw database (835 instances) ships only `hamiltonian_projected.npy` -- no
decompositions.  Validated by diffing against her 20 instances.

Convention (verified: raw npy reproduces her couplings to 2.8e-17):
    het bond (i<nc) XOR (j<nc)  ->  ZZ with coeff = +d_ij
    hom bond                    ->  XX with coeff = -d_ij  AND  YY with coeff = +d_ij
Structure:
    mincoloring : 3 groups = [all XX], [all YY], [all ZZ], each in lexicographic (i,j) order
    descending  : one term per group, sorted by |coeff| descending
    ascending   : one term per group, sorted by |coeff| ascending
Ties (XX/YY on one bond always share |d|) are broken by the BASE order, which the --tiebreak
option selects; `yx` (YY before XX) is the one that matches her files.

  python3 gen_orderings.py --validate      # diff against all 20 of her instances
"""
import argparse
import glob
import json
import os
import numpy as np

DB = 'google-nmr/google_generated_hamiltonians_2026_02_02/data/converged_instances'


def base_terms(M, nc=2, tiebreak='yx'):
    """Canonical base list, lexicographic in (i,j); tiebreak sets XX/YY order within a bond."""
    N = M.shape[0]
    out = []
    for i in range(N):
        for j in range(i + 1, N):
            d = float(M[i, j])
            if d == 0.0:
                continue
            if (i < nc) ^ (j < nc):
                out.append((i, j, 'ZZ', d))
            else:
                pair = [(i, j, 'YY', d), (i, j, 'XX', -d)]
                if tiebreak == 'xy':
                    pair = pair[::-1]
                out.extend(pair)
    return out


def orderings(M, nc=2, tiebreak='yx'):
    t = base_terms(M, nc, tiebreak)
    xx = [x for x in t if x[2] == 'XX']
    yy = [x for x in t if x[2] == 'YY']
    zz = [x for x in t if x[2] == 'ZZ']
    out = {
        'mincoloring': [xx, yy, zz],
        'mincoloring_xzy': [xx, zz, yy],
        'mincoloring_zxy': [zz, xx, yy],
        'descending': [[x] for x in sorted(t, key=lambda v: -abs(v[3]))],
        'ascending': [[x] for x in sorted(t, key=lambda v: abs(v[3]))],
    }
    out.update(interaction_orderings(M, nc, tiebreak))
    out.update(swapnet_ordering(M, nc, tiebreak))
    return out


def swapnet_schedule(N):
    """Odd-even transposition swap-network schedule over N positions.

    -> one list of (qubit_i, qubit_j) pairs per round, read off the current position->qubit array.
    Round r pairs adjacent POSITIONS starting at r&1 (even rounds (0,1),(2,3),...; odd rounds
    (1,2),(3,4),...), interacts them, then swaps them. Over N rounds the network is a bubble sort,
    so every unordered qubit pair becomes adjacent EXACTLY ONCE -- all N(N-1)/2 of them, with no
    repetition, which is what makes the emitted list a permutation of the Hamiltonian's terms.

    Ported byte-compatibly from Charlie's `orderings.swapnet_schedule` (validated by
    gen_orderings.py --validate-swapnet against his own function on the raw database).
    """
    positions = list(range(N))            # positions[p] = qubit currently at position p
    rounds = []
    for rnd in range(N):
        position_pairs = [(p, p + 1) for p in range(rnd & 1, N - 1, 2)]
        rounds.append([(positions[pa], positions[pb]) for pa, pb in position_pairs])
        for pa, pb in position_pairs:
            positions[pa], positions[pb] = positions[pb], positions[pa]
    return rounds


def swapnet_ordering(M, nc=2, tiebreak='yx'):
    """Charlie's `swapnet`: interactions in odd-even transposition swap-network order.

    This is the PURE ordering -- all-to-all connectivity is assumed and no physical SWAP gates are
    emitted. The network only fixes WHICH interactions are adjacent in the term sequence.

    One group per round. Within a round the interacted pairs are qubit-disjoint, and XX/YY on one
    bond commute with each other, so a whole round is mutually commuting and the group is exact --
    unlike `descending`/`ascending`, which can only be one term per group. (The grouping is
    presentational for the circuit itself: TrotterV flattens `groups` for the forward half and
    fully reverses it for the backward half, so only the FLAT term order reaches the schedule.)

    Charlie sorts each pair's terms by |coeff| descending. XX and YY on one bond always share |d|,
    so that sort is a no-op under a stable sort and the pair keeps its `base_terms` order -- the
    same `tiebreak` convention every other ordering here uses.
    """
    N = M.shape[0]
    by_pair = {}
    for term in base_terms(M, nc, tiebreak):
        by_pair.setdefault((term[0], term[1]), []).append(term)
    groups = []
    for rnd in swapnet_schedule(N):
        layer = []
        for qi, qj in rnd:
            layer.extend(by_pair.get((min(qi, qj), max(qi, qj)), []))
        if layer:
            groups.append(layer)
    return {'swapnet': groups}


def interaction_orderings(M, nc=2, tiebreak='yx'):
    """Charlie confirmed (2026-08-08, "Request for Alberto.pdf"): INTERACTION weight differs
    from Pauli-TERM weight (the plain ascending/descending above) -- split H into pair
    interactions (aZZ hetero, or b(XX-YY) homo, evolved EXACTLY as that one interaction, not as
    two separate XX/YY exponentials), ordered by the operator norm of the WHOLE interaction:
    |a| for aZZ, 2|b| for b(XX-YY) (since XX-YY has operator norm 2). Validated byte-for-byte
    against his worked example (H = ZZI + 2/3(IXX-IYY) -> descending = [2/3(IXX-IYY), ZZI],
    since |2/3*2|=4/3 > 1).

    XX and YY on the same bond commute exactly ([XX,YY]=0, since XX.YY=YY.XX=-ZZ), so grouping
    them as one TrotterV group (applied back-to-back, never split by another bond's terms) is
    mathematically IDENTICAL to a genuine combined exp(-i tau b(XX-YY)) block -- no separate
    "exact 2-qubit gate" implementation is needed, the existing per-term rotation machinery
    already gives the exact combined result as long as the pair stays adjacent, which grouping
    them together guarantees.
    """
    N = M.shape[0]
    bonds = []
    for i in range(N):
        for j in range(i + 1, N):
            d = float(M[i, j])
            if d == 0.0:
                continue
            if (i < nc) ^ (j < nc):
                bonds.append((abs(d), [(i, j, 'ZZ', d)]))
            else:
                pair = [(i, j, 'YY', d), (i, j, 'XX', -d)]
                if tiebreak == 'xy':
                    pair = pair[::-1]
                bonds.append((2 * abs(d), pair))
    return {
        'interaction_descending': [terms for _, terms in sorted(bonds, key=lambda b: -b[0])],
        'interaction_ascending': [terms for _, terms in sorted(bonds, key=lambda b: b[0])],
    }


def her_groups(jf):
    d = json.load(open(jf))
    out = {}
    for o in ('mincoloring', 'descending', 'ascending'):
        if o not in d:
            continue
        g = []
        hd = d[o]['hamiltonian_decomposition']
        for k in sorted(hd, key=int):
            terms = []
            for kk in sorted(hd[k], key=int):
                tm = hd[k][kk]
                s = sorted(int(q) for q in tm if q != 'coeff')
                pl = ''.join(tm[str(q)] for q in s)
                c = tm['coeff']
                c = float(c['re']) if isinstance(c, dict) else float(c)
                terms.append((s[0], s[1], pl, c))
            g.append(terms)
        out[o] = g
    return d['n'], out


def diff(mine, hers, tol=1e-12):
    """-> (structure_ok, worst coeff deviation, first mismatch description)"""
    if len(mine) != len(hers):
        return False, np.inf, 'group count %d vs %d' % (len(mine), len(hers))
    worst = 0.0
    for gi, (a, b) in enumerate(zip(mine, hers)):
        if len(a) != len(b):
            return False, np.inf, 'group %d size %d vs %d' % (gi, len(a), len(b))
        for ti, (x, y) in enumerate(zip(a, b)):
            if (x[0], x[1], x[2]) != (y[0], y[1], y[2]):
                return False, np.inf, 'group %d term %d: %s vs %s' % (gi, ti, x[:3], y[:3])
            worst = max(worst, abs(x[3] - y[3]))
    return worst <= tol, worst, ''


def validate_swapnet(nc=2, tiebreak='yx', limit=0):
    """Diff `swapnet` against Charlie's own `orderings.order_swapnet` on the raw database.

    His function is re-implemented inline rather than imported: `orderings.py` pulls in networkx,
    `min_steps_common` and two packages from his repo, none of which the compute hosts have -- and
    the point of the check is the ALGORITHM, which is 12 lines. -> (checked, mismatches).
    """
    import openfermion as of

    def his_schedule(n):
        positions = list(range(n))
        out = []
        for rnd in range(n):
            pairs = [(p, p + 1) for p in range(rnd & 1, n - 1, 2)]
            out.append([(positions[pa], positions[pb]) for pa, pb in pairs])
            for pa, pb in pairs:
                positions[pa], positions[pb] = positions[pb], positions[pa]
        return out

    def his_order(ham, n):
        by_pair = {}
        for term, coeff in ham.terms.items():
            if term == ():
                continue
            by_pair.setdefault(frozenset(q for q, _ in term), []).append((term, coeff))
        out = []
        for rnd in his_schedule(n):
            for qi, qj in rnd:
                terms = by_pair.get(frozenset((qi, qj)))
                if terms:
                    out += sorted(terms, key=lambda tc: -abs(tc[1]))
        assert set(t for t, _ in out) == set(t for t in ham.terms if t != ())
        return out

    insts = sorted(glob.glob(os.path.join(DB, 'instance_*')))
    if limit:
        insts = insts[:limit]
    checked = bad = 0
    for d in insts:
        raw = os.path.join(d, 'hamiltonian_projected.npy')
        if not os.path.exists(raw):
            continue
        M = np.load(raw)
        N = M.shape[0]
        base = base_terms(M, nc, tiebreak)
        mine = [x for g in swapnet_ordering(M, nc, tiebreak)['swapnet'] for x in g]
        ham = of.QubitOperator()
        for i, j, pl, c in base:
            ham += of.QubitOperator(((i, pl[0]), (j, pl[1])), c)
        his = []
        for term, c in his_order(ham, N):
            (qi, pi), (qj, pj) = sorted(term)
            his.append((qi, qj, pi + pj, float(np.real(c))))
        checked += 1
        same = len(mine) == len(his) and all(
            a[:3] == b[:3] and abs(a[3] - b[3]) <= 1e-15 for a, b in zip(mine, his))
        if not same or sorted(mine) != sorted(base):
            bad += 1
            if bad <= 3:
                print('    MISMATCH %s (N=%d)' % (os.path.basename(d), N))
    return checked, bad


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--validate', action='store_true')
    ap.add_argument('--validate-swapnet', action='store_true',
                    help="diff `swapnet` against Charlie's order_swapnet over the raw database")
    ap.add_argument('--limit', type=int, default=0, help='with --validate-swapnet: first K only')
    ap.add_argument('--tiebreak', default='both', choices=['yx', 'xy', 'both'])
    ap.add_argument('--nc', type=int, default=2)
    a = ap.parse_args()

    if a.validate_swapnet:
        checked, bad = validate_swapnet(nc=a.nc, tiebreak='yx', limit=a.limit)
        print('swapnet: %d instances checked, %d mismatches vs order_swapnet' % (checked, bad))
        raise SystemExit(1 if bad else 0)

    jfs = sorted(glob.glob('n10z2/10_qubit_instances_2/*.json')) + \
        sorted(glob.glob('n11z/11_qubit_instances_2/*.json'))
    tbs = ['yx', 'xy'] if a.tiebreak == 'both' else [a.tiebreak]
    for tb in tbs:
        ok = fail = 0
        worst = 0.0
        msgs = []
        for jf in jfs:
            inst = os.path.basename(jf)[:-5]
            raw = os.path.join(DB, inst, 'hamiltonian_projected.npy')
            if not os.path.exists(raw):
                continue
            M = np.load(raw)
            N, hers = her_groups(jf)
            mine = orderings(M, nc=a.nc, tiebreak=tb)
            for o in hers:
                good, w, msg = diff(mine[o], hers[o])
                if good:
                    ok += 1
                    worst = max(worst, w)
                else:
                    fail += 1
                    if len(msgs) < 3:
                        msgs.append('%s/%s: %s' % (inst, o, msg))
        print('tiebreak=%-3s  exact matches %d, mismatches %d, worst coeff dev %.2e'
              % (tb, ok, fail, worst))
        for m in msgs:
            print('    ', m)
