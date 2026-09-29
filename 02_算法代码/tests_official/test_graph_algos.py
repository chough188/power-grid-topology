import unittest

from shared.graph_algos import (
    adjacency_from_terminals,
    articulation_points,
    bfs,
    connected_components,
    find_cycles,
    has_cycle,
    shortest_path,
)


class GraphAlgoTests(unittest.TestCase):
    def setUp(self):
        # Triangle A-B-C + tail C-D, isolated pair E-F
        self.adj = {
            'A': {'B', 'C'},
            'B': {'A', 'C'},
            'C': {'A', 'B', 'D'},
            'D': {'C'},
            'E': {'F'},
            'F': {'E'},
        }

    def test_bfs_visits_all_reachable(self):
        visited = bfs(self.adj, 'A')
        self.assertEqual(set(visited), {'A', 'B', 'C', 'D'})

    def test_connected_components_finds_two(self):
        cc = connected_components(self.adj)
        self.assertEqual(len(cc), 2)
        sizes = sorted(len(c) for c in cc)
        self.assertEqual(sizes, [2, 4])

    def test_has_cycle_true_for_triangle(self):
        self.assertTrue(has_cycle(self.adj))

    def test_find_cycles_returns_triangle(self):
        cycles = find_cycles(self.adj, max_cycles=10)
        self.assertGreater(len(cycles), 0)
        for c in cycles:
            self.assertGreaterEqual(len(c), 3)

    def test_shortest_path_simple(self):
        self.assertEqual(shortest_path(self.adj, 'A', 'D'), ('A', 'C', 'D'))

    def test_shortest_path_unreachable(self):
        self.assertIsNone(shortest_path(self.adj, 'A', 'E'))

    def test_articulation_points_finds_C(self):
        ap = articulation_points(self.adj)
        self.assertIn('C', ap)

    def test_adjacency_from_terminals_builds_correctly(self):
        tables = {
            'JBS_PWTERMINAL': [
                {'EQUIP_ID': 'E1', 'CONNECTIVITYNODE_ID': 'N1'},
                {'EQUIP_ID': 'E1', 'CONNECTIVITYNODE_ID': 'N2'},
                {'EQUIP_ID': 'E2', 'CONNECTIVITYNODE_ID': 'N2'},
                {'EQUIP_ID': 'E2', 'CONNECTIVITYNODE_ID': 'N3'},
            ],
        }
        adj = adjacency_from_terminals(tables)
        # N1-N2 and N2-N3 should be edges via shared E1/E2
        self.assertIn('N1', adj['N2'])
        self.assertIn('N3', adj['N2'])
        self.assertEqual(adj['N1'], {'N2'})


if __name__ == '__main__':
    unittest.main()
