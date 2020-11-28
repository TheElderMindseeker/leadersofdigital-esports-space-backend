from typing import Dict, Tuple, List


class PlayOff:

    def __init__(self, sequence: List[int], matches: Dict[Tuple[int, int], int]):
        self.leaves = len(sequence)
        self.tree = [self.tbd] * self.leaves
        self.tree.extend(sequence)

        for index in range(self.leaves - 1, 0, -1):
            v_left, v_right = self.tree[self.left(index)], self.tree[self.right(index)]
            if self.is_id(v_left) and self.is_id(v_right):
                key = (v_left, v_right)
                self.tree[index] = matches.get(key, self.tbd)
            elif self.is_no_match(v_left):
                self.tree[index] = v_right
            elif self.is_no_match(v_right):
                self.tree[index] = v_left

    def is_finished(self):
        return self.is_id(self.tree[self.root])

    def next_match_for(self, pl_id: int):
        if self.is_finished():
            return {'state': 'finished', 'id': -1}
        for index in range(self.root, len(self.tree)):
            if self.tree[index] == pl_id:
                if self.is_tbd(self.tree[self.parent(index)]):
                    v_sibling = self.tree[self.sibling(index)]
                    if self.is_tbd(v_sibling):
                        return {'state': 'TBD', 'id': -1}
                    return {'state': 'defined', 'id': v_sibling}
                else:
                    return {'state': 'lost', 'id': -1}
        raise ValueError(f'{pl_id} is not a participant of this tournament')

    @staticmethod
    def is_id(number):
        return number >= 0

    def is_no_match(self, number):
        return number == self.no_match

    def is_tbd(self, number):
        return number == self.tbd

    @staticmethod
    def left(index):
        return index * 2

    @staticmethod
    def right(index):
        return index * 2 + 1

    @staticmethod
    def parent(index):
        return index // 2

    def sibling(self, index):
        if self.is_left(index):
            return self.right(self.parent(index))
        else:
            return self.left(self.parent(index))

    def is_root(self, index):
        return index == self.root

    def is_left(self, index):
        if self.is_root(index):
            raise ValueError('Root has no siblings')
        return index % 2 == 0

    def is_right(self, index):
        return not self.is_left(index)

    root = 1
    no_match = -1
    tbd = -2
