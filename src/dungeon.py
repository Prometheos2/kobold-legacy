import math
import random

from encounter import Encounter
from tile import Tile

from ..kobold import OPP_DIR
from ..kobold import chance
from ..kobold import choice
from ..kobold import console_print
from ..kobold import dungeon_data
from ..kobold import forage
from ..kobold import spawn_item


class Dungeon:
    def __init__(self, type, world, x, y, z):
        self.world = world
        self.x = x
        self.y = y
        self.z = z
        self.id = self.world.did
        self.world.did += 1
        self.map = {}
        self.d = type
        world.dungeons.append(self)
        self.generate()

    def get_tile(self, x, y, z, gen=True):
        if x < 0:
            return None
        elif x > dungeon_data[self.d]["dimensions"][0]:
            return None
        elif y < 0:
            return None
        elif y > dungeon_data[self.d]["dimensions"][1]:
            return None
        elif z < 0:
            return None
        elif z > dungeon_data[self.d]["dimensions"][2]:
            return None
        m = str(x)+","+str(y)+","+str(z)
        #console_print("getting tile "+m)
        if m in self.map:
            return self.map[m]
        elif gen:
            self.map[m] = Tile(self.world, x, y, z, self)
            if chance(50):
                forage(self.map[m], dgn=self)
            if "Locked Doors" in dungeon_data[self.d].get("hazards", []):
                for x in ["n", "w", "e", "s"]:
                    if not self.map[m].blocked[x] and chance(10):
                        self.map[m].locked[x] = True
                        kr = choice(list(self.map.keys()))
                        done = False
                        for e in self.world.encounters:
                            if e.place == self.map[kr]:
                                c = choice(e.creatures)
                                if not c:
                                    continue
                                c.loot.append(["Dungeon Key", 1, 1, 100])
                                done = True
                        if not done:
                            spawn_item("Dungeon Key", self.map[kr])
            return self.map[m]
        else:
            return None

    def expand(self, gpos):
        ot = self.get_tile(gpos[0], gpos[1], gpos[2])
        dirs = ["n", "e", "w", "s", "u", "d"]
        if gpos[0] == 0:
            dirs.remove("w")
        if gpos[0] == dungeon_data[self.d]["dimensions"][0]:
            dirs.remove("e")
        if gpos[1] == 0:
            dirs.remove("n")
        if gpos[1] == dungeon_data[self.d]["dimensions"][1]:
            dirs.remove("s")
        if gpos[2] == 0:
            dirs.remove("u")
        if gpos[2] == dungeon_data[self.d]["dimensions"][2]:
            dirs.remove("d")
        dir = choice(dirs)
        npos = list(gpos)
        if dir == "w":
            npos[0] -= 1
        elif dir == "e":
            npos[0] += 1
        elif dir == "n":
            npos[1] -= 1
        elif dir == "s":
            npos[1] += 1
        elif dir == "u":
            npos[2] -= 1
        elif dir == "d":
            npos[2] += 1
        nt = self.get_tile(npos[0], npos[1], npos[2])
        console_print("expanding "+str(gpos)+" to "+str(npos))
        if dir == "u":
            if "Stairs Up" not in ot.special:
                ot.special.append("Stairs Up")
            if "Stairs Down" not in nt.special:
                nt.special.append("Stairs Down")
        elif dir == "d":
            if "Stairs Up" not in nt.special:
                nt.special.append("Stairs Up")
            if "Stairs Down" not in ot.special:
                ot.special.append("Stairs Down")
        else:
            ot.blocked[dir] = False
            nt.blocked[OPP_DIR[dir]] = False
        return npos

    def generate(self):
        self.entry = (random.randint(0, dungeon_data[self.d]["dimensions"][0]), random.randint(
            0, dungeon_data[self.d]["dimensions"][1]), random.randint(0, dungeon_data[self.d]["dimensions"][2]))
        firstile = self.get_tile(self.entry[0], self.entry[1], self.entry[2])
        firstile.special.append("Dungeon Exit")
        gpos = list(self.entry)
        for x in range(dungeon_data[self.d]["bosslength"]):
            npos = self.expand(gpos)
            if chance(50):
                for xx in range(random.randint(1, math.ceil(dungeon_data[self.d]["bosslength"]/2))):
                    self.expand(gpos)
            if chance(50):
                for xx in range(random.randint(1, math.ceil(dungeon_data[self.d]["bosslength"]/2))):
                    self.expand(gpos)
            gpos = npos
        bosstile = self.get_tile(gpos[0], gpos[1], gpos[2])
        for e in self.world.encounters:
            if e.place == bosstile:
                self.world.encounters.remove(e)
                break
        enc = Encounter(self.world, bosstile, 0, 0, force="Ant")
        enc.special = dungeon_data[self.d]["boss"][0]
        for c in dungeon_data[self.d]["boss"]:
            a = c.split(":")
            if len(a) > 1:
                am = int(a[1])
            else:
                am = 1
            enc.populate(a[0], am)
        if dungeon_data[self.d].get("boss_landmark", None):
            bosstile.special.append(dungeon_data[self.d]["boss_landmark"])
