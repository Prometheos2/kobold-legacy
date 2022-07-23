import math
import random
import time

import discord

from creature import Creature
from dungeon import Dungeon
from encounter import Encounter

from ..kobold import DIR_FULL
from ..kobold import OPP_DIR
from ..kobold import action_queue
from ..kobold import building_data
from ..kobold import chance
from ..kobold import check_req
from ..kobold import choice
from ..kobold import console_print
from ..kobold import consume_item
from ..kobold import dungeon_data
from ..kobold import game_print
from ..kobold import get_dir
from ..kobold import has_item
from ..kobold import item_data
from ..kobold import landmark_data
from ..kobold import spawn_item


class Tile:
    def __init__(self, world, x, y, z, dungeon=None):
        self.x = x
        self.y = y
        self.z = z
        self.world = world
        self.mineprog = {"n": 0, "e": 0, "w": 0, "s": 0}
        self.items = []
        self.resources = {"n": None, "e": None, "w": None, "s": None}
        self.mined = {"n": 0, "e": 0, "w": 0, "s": 0}
        if z > 0:
            self.stability = random.randint(90, 110)
        else:
            self.stability = random.randint(0, 20)
        self.blocked = {"n": False, "e": False, "s": False, "w": False}
        self.locked = {"n": False, "e": False, "s": False, "w": False}
        self.camp = None
        self.special = []
        self.pasture = []
        self.building_prog = {}
        self.building_relay = {}
        borders = [(x+1, y, z), (x-1, y, z), (x, y+1, z), (x, y-1, z)]
        dirs = ["e", "w", "s", "n"]
        self.farm_cap = 0
        self.farming_prog = {}
        self.dungeon = dungeon
        if dungeon:
            if chance(50):
                self.spawn_encounter(
                    choice(dungeon_data[dungeon.d]["spawns"]), dungeon_data[dungeon.d]["cr"])
        elif not self.get_tribe() and not (x == 0 and y == 0):
            if chance(40):
                self.spawn_encounter()
            if chance(30):
                self.landmarks()
        if dungeon or z > 0:
            if not dungeon:
                self.minerals()
            for x in range(4):
                if dungeon:
                    t = dungeon.get_tile(
                        borders[x][0], borders[x][1], borders[x][2], False)
                else:
                    t = self.world.get_tile(
                        borders[x][0], borders[x][1], borders[x][2], False)
                if t:
                    self.blocked[dirs[x]] = t.blocked[OPP_DIR[dirs[x]]]
                elif dungeon or chance(50):
                    self.blocked[dirs[x]] = True

    @property
    def space_in_use(self):
        bolds = []
        csp = 0
        for k in self.world.kobold_list:
            if k.get_place() == self:
                bolds.append(k)
                if k.party and k.party.owner == k:
                    for c in k.party.c_members:
                        csp += c.corpse["size"]
        sp = len(bolds)
        sp += math.floor(csp/2)
        return sp

    def minerals(self):
        possible = {}
        for i in item_data:
            ml = i.get("minelevel", 0)
            if ml > 0 and ml <= self.z:
                possible[i["name"]] = i["chance"]
        reses = []
        for p in possible:
            if chance(possible[p]):
                reses.append(p)
        while len(reses) < 4:
            reses.append(None)
        random.shuffle(reses)
        for d in self.mined:
            if not self.resources[d]:
                self.mined[d] = random.randint(0, 4)-4
                self.resources[d] = reses.pop(0)
                if self.resources[d] and chance(20):
                    spawn_item(self.resources[d], self)

    def landmarks(self):
        wt = 0
        ls = []
        for l in landmark_data:
            if self.z >= landmark_data[l]["level"][0] and (self.z <= landmark_data[l]["level"][1] or landmark_data[l]["level"][1] == -1):
                wt += landmark_data[l]["weight"]
                ls.append(l)
        r = random.randint(1, wt)
        while r > 0:
            l = ls.pop(0)
            r -= landmark_data[l]["weight"]
        self.special.append(l)

    def get_dungeon(self):
        for t in self.world.dungeons:
            if (t.x, t.y, t.z) == (self.x, self.y, self.z):
                return t
        for x in self.special:
            if landmark_data[x].get("dungeon", None):
                return Dungeon(landmark_data[x]["dungeon"], self.world, self.x, self.y, self.z)
        return None

    def get_tribe(self):
        if self.get_dungeon():
            return None
        for t in self.world.tribes:
            if (t.x, t.y, t.z) == (self.x, self.y, self.z):
                return t
        return None

    def cave_in(self, me, dir=None):
        if dir and self.blocked[dir]:
            return
        if dir:
            ch = 100-self.stability-(me.skmod("mining")*5)
        else:
            ch = 100-self.stability
        tribe = self.get_tribe()
        if tribe and tribe.has_building("Stone Pillars"):
            ch = math.floor(ch/2)
        if chance(ch):
            bolds = []
            if dir:
                msg = me.display()+"'s mining has caused a cave-in! Rocks are falling everywhere!"
                msg += "\nThe tunnel to the " + \
                    DIR_FULL[dir]+" has been completely filled with rocks."
            else:
                msg = "A cave-in has occurred! Rocks are falling everywhere!"
            me.p(msg)
            if me.party:
                me.broadcast(msg)
            for k in self.world.kobold_list:
                if (k.x, k.y, k.z) == (self.x, self.y, self.z):
                    if tribe and tribe.has_building("Nursery") and k.age < 6:
                        continue
                    bolds.append(k)
            for k in bolds:
                if k.save("dex") < 11:
                    dmg = random.randint(1, 15)
                    if k.worns["body"] and k.worns["body"].name == "Work Gear":
                        dmg = math.ceil(dmg/2)
                    k.hp_tax(dmg, "Cave-in")
            if dir:
                self.blocked[dir] = True
                self.get_border(dir).blocked[OPP_DIR[dir]] = True
            self.stability += 50

    def invasion(t):
        bolds = []
        neut = True
        chan = None
        for k in t.world.kobold_list:
            if k.get_place() == t:
                bolds.append(k)
                if k.get_chan() != "exception-log":
                    chan = k.get_chan()
            if k.tribe and not k.tribe.shc_faction["Goblin"] < 1:
                neut = False
        if t.camp:
            if neut:
                game_print(
                    "The goblins have passed this camp by thanks to the truce.", chan)
                return
            invasion = int(t.camp["heat"]*random.randint(80, 120)/100)
            if t.camp.get("magic", False):
                t.camp = {}
                if chan:
                    game_print("The Tiny Hut vanishes.", chan)
            elif invasion > 0:
                game_print(
                    str(invasion)+" goblins have discovered the camp and attack!", chan)
                defense = t.camp["defense"]
                dmg = 0
                dmgto = {}
                if defense+5 < t.space_in_use:
                    outside = t.space_in_use-(defense+5)
                    game_print(
                        "Some kobolds were caught sleeping outside! This wouldn't happen if we had enough space for everyone...", chan)
                    for x in range(outside):
                        k = choice(bolds)
                        if k:
                            k.hp_tax(random.randint(1, invasion), "Slept in the open", dmgtype=choice(
                                ["bludgeoning", "slashing", "piercing"]))
                            bolds.remove(k)
                if invasion > defense and len(t.camp["watch"]) > 0:
                    dmg = invasion-defense
                    game_print(
                        "The invaders broke through our outer defenses. Our watchmen are the only thing between us and certain doom.", chan)
                    for x in range(dmg):
                        target = choice(t.camp["watch"])
                        if isinstance(target, Creature):
                            tn = target.name
                        else:
                            tn = str(target.id)
                        if tn in dmgto:
                            dmgto[tn] += 1
                        else:
                            dmgto[tn] = 1
                    wm = list(t.camp["watch"])
                    for k in wm:
                        defense += k.watch_damage(dmg, dmgto)
                if invasion > defense:
                    game_print(
                        "The invaders have breached our defenses!", chan)
                    dmg = invasion-defense
                    dmgto = {}
                    targets = ["kobold", "building", "item"]
                    for x in range(dmg):
                        hit = choice(targets)
                        if hit == "item" and len(t.items) > 0:
                            target = choice(t.items)
                            target.destroy("Lost in raid")
                            game_print(target.display() +
                                       " was lost in the raid!", chan)
                        elif len(bolds) > 0:
                            target = choice(bolds)
                            if str(target.id) in dmgto:
                                dmgto[str(target.id)] += 2
                            else:
                                dmgto[str(target.id)] = 2
                        else:
                            t.camp["defense"] -= 1
                    for k in bolds:
                        if str(k.id) in dmgto:
                            k.hp_tax(dmgto[str(k.id)], "Civilian casualty", dmgtype=choice(
                                ["bludgeoning", "slashing", "piercing"]))
                        if k.save("wis") < 12:
                            k.add_trait("stressed")
                    game_print("The attack is finally over.", chan)
                else:
                    game_print(
                        "The invaders could not reach the camp. We have made it through the raid.", chan)
                if t.camp["defense"] < 0:
                    t.camp = {}
                    game_print("The camp was destroyed!", chan)
                    console_print("Camp destroyed at " +
                                  str((t.x, t.y, t.z)), hp=True)
                else:
                    near = 0
                    tils = t.world.scan(t, 3, False)
                    for m in tils:
                        if t.world.map[m] != t and (t.world.map[m].camp or t.world.map[m].get_tribe()):
                            near += 1
                    t.camp["heat"] += len(bolds)*(1.5**near)
                    t.camp["watch"] = []
            else:
                t.camp["heat"] += 1
        elif len(bolds) > 0:
            if chan:
                game_print(
                    "A marauding band of goblins passes through the area...", chan)
            for k in bolds:
                if neut:
                    k.p("[n] has nothing to worry about as the goblins have called a truce.")
                elif chance(k.hiding) and not k.encounter:
                    k.die("Unprotected traveler")
                else:
                    k.p("[n] survived the night completely undetected.")
                    ct = k.world.find_tile_feature(
                        10, t, "Goblin Camp", "special")
                    if ct:
                        dir = get_dir(ct, k)
                        if dir != "same":
                            k.p("[n] watches the goblins head " +
                                dir+" back to their camp.")
                        k.gain_xp("stealth", 100)
        if t.farm_cap > 0:
            if "Scarecrow" in t.special and chance(34):
                return
            oldspace = t.farm_cap
            decay = max(math.floor(t.farm_cap/4), 50)
            if "Farm Fencing" in t.special:
                decay = math.floor(decay/2)
            t.farm_cap -= decay
            tribe = t.get_tribe()
            if tribe:
                sp = math.floor(oldspace/100) - \
                    math.floor(max(t.farm_cap, 0)/100)
                tribe.space += sp
            if t.farm_cap <= 0:
                if chan:
                    game_print("The farm was destroyed!", chan)
                for l in t.special:
                    if "Farm" in l:
                        t.special.remove(l)
            elif chan:
                game_print("The farm was damaged!", chan)
            if "Scarecrow" in t.special and chance(50-(t.farm_cap/10)):
                if chan:
                    game_print("The Scarecrow was destroyed!", chan)
                t.special.remove("Scarecrow")
            if "Farm Fencing" in t.special and chance(50-(t.farm_cap/10)):
                if chan:
                    game_print("The Farm Fencing was destroyed!", chan)
                t.special.remove("Farm Fencing")

    def spawn_encounter(self, force=None, n=0):
        for e in self.world.encounters:
            if e.place == self:
                return
        mindist = 9999
        if len(self.world.tribes) <= 0:
            return  # can't spawn if no tribes
        ct = None
        if self.z > 0:
            for t in self.world.tribes:
                disto = abs(self.x-t.x)+abs(self.y-t.y)
                if disto == 0:
                    console_print("encounter spawning failed, on tribe")
                    return  # can't spawn on a tribe
                if disto < mindist:
                    scale = (t.month+len(t.research)+disto)/2
                    rt = math.floor((math.sqrt((8*scale)+1)-1)/2)
                    mindist = disto+math.floor(rt)
        if n == 0:
            if self.z == 0:
                n = random.randint(5, 10)
            elif self.z == 1:
                n = math.floor((math.sqrt((8*mindist)+1)-1)/2)
                console_print([mindist, n])
            else:
                n = random.randint(self.z*3, self.z*8)
            if "Warding Lantern" in self.special:
                n = math.floor(n/2)
        e = Encounter(self.world, self, random.randint(
            n, int(n*1.5)+2), self.z, force)

    def get_party(self):
        partieshere = []
        for k in self.world.kobold_list:
            if k.party and k.get_place() == self and k.party not in partieshere:
                partieshere.append(k.party)
        return partieshere

    def get_border(self, d):
        borders = {"e": (self.x+1, self.y, self.z), "w": (self.x-1, self.y, self.z),
                   "s": (self.x, self.y+1, self.z), "n": (self.x, self.y-1, self.z)}
        t = self.world.get_tile(borders[d][0], borders[d][1], borders[d][2])
        return t

    def item_quantities(self):
        q = {}
        for i in self.items:
            if i.name not in q:
                q[i.name] = i.num
            else:
                q[i.name] += i.num
        return q

    def get_available_builds(self, k=None):
        ar = []
        for r in building_data:
            good = True
            if not r.get("landmark", False):
                good = False
            else:
                if r["name"] in self.special and not r.get("repeatable", False):
                    good = False
                if "Farm" in r["name"]:
                    for l in self.special:
                        if "Farm" in l:
                            good = False
                allitems = self.item_quantities()
                for m in r.get("materials", []):
                    gra = m.split("/")
                    g = False
                    for b in gra:
                        arg = b.split(":")
                        if len(arg) == 1:
                            arg.append(1)
                        if self.has_item(arg[0], int(arg[1])):
                            g = True
                    if good:
                        good = g
                if good:
                    g = check_req(None, r.get("req", []), k)
                    if g != "good":
                        good = False
            if good:
                ar.append(r["name"])
        return ar

    def do_building(self, k, res):
        prog = (k.smod("str")+(k.skmod("construction")*3))+10
        prog += k.equip_bonus("construction")
        r = res["name"]
        if r not in self.building_relay:
            self.building_relay[r] = {}
        if str(k.id) not in self.building_relay[r]:
            self.building_relay[r][str(k.id)] = 0
        relays = 10
        for a in self.building_relay[r]:
            if a == str(k.id):
                continue
            relays += self.building_relay[r][a]
        prog = int(prog*(1-(self.building_relay[r][str(k.id)]/relays)))
        self.building_relay[r][str(k.id)] += 1
        prog = max(1, prog)
        if r not in self.building_prog:
            self.building_prog[r] = 0
        self.building_prog[r] += prog
        k.p("[n] has made "+str(prog)+" progress building "+r +
            ". ("+str(self.building_prog[r])+"/"+str(res["work"])+")")
        exp = prog
        if self.building_prog[r] >= res["work"]:
            k.p("[n] has finished construction of "+r+"!")
            self.finish_building(res, k)
            exp += min(prog*4, res["work"]/4)
        k.gain_xp("construction", exp)
        k.gain_fam(res.get("req", []), prog)

    def finish_building(self, res, k):
        self.special.append(res["name"])
        self.building_prog[res["name"]] = 0
        t = self.get_tribe()
        if t:
            t.space -= res.get("space", 0)
        needs = res.get("materials", [])
        if k.tribe:
            k.tribe.justbuilt = res["name"]
        if k:
            place = k.get_place()
        else:
            place = self
        for n in needs:
            gra = n.split("/")
            for b in gra:
                arg = b.split(":")
                if len(arg) == 1:
                    arg.append(1)
                if place.has_item(arg[0], int(arg[1])):
                    place.consume_item(arg[0], int(arg[1]))
                    break
                else:
                    console_print("Could not consume "+b +
                                  " when building "+res["name"]+".", True)
        if " Farm" in res["name"]:
            self.farm_cap = 200  # silly but effective fix for "farm fencing" resetting cap
        if res["name"] == "Paved Road" and "Road" in self.special:
            self.special.remove("Road")
        if res["name"] == "Bracing":
            self.stability += 20
        if res["name"] == "Aqueduct":
            if k.tribe:
                k.tribe.wpm += 5
        if res["name"] == "Stairs Up":
            st = self.world.get_tile(self.x, self.y, self.z-1)
            if "Stairs Down" not in st.special:
                st.special.append("Stairs Down")
        if res["name"] == "Stairs Down":
            st = self.world.get_tile(self.x, self.y, self.z+1)
            if "Stairs Up" not in st.special:
                st.special.append("Stairs Up")
        if res["name"] == "Quarry":
            spawn_item("Stone Chunk", self, 10)
            self.minerals()

    def unfinish_building(self, res):
        self.special.remove(res["name"])

    def has_item(self, name, q=1):
        return has_item(self, name, q)

    def consume_item(self, name, q=1):
        return consume_item(self, name, q)

    def item_quantities(self):
        q = {}
        for i in self.items:
            if i.name not in q:
                q[i.name] = i.num
            else:
                q[i.name] += i.num
        return q

    def get_chan(self):
        tribe = self.get_tribe()
        if tribe:
            return tribe.get_chan()
        for k in self.world.kobold_list:
            if k.get_place() == self:
                return k.get_chan()

    def examine(self, me):
        dgn = me.dungeon
        if dgn:
            title = dungeon_data[dgn.d]["name"]+", level "+str(self.z)
        else:
            title = "Overworld, level "+str(self.z)
        msg = "Time until month change: "
        sec = me.world.next_mc_time-time.time()
        if sec > 0:
            h = int(math.floor(float(sec/3600)))
            m = int(math.floor(float((sec % 3600)/60)))
            s = int(sec % 60)
            msg += str(h)+"h, "+str(m)+"m, "+str(s)+"s\n\n"
        else:
            msg += "Any moment now...\n\n"
        msg += "Available directions: "
        dirs = []
        nirs = []
        if not hasattr(self, "locked"):
            self.locked = {"n": False, "e": False, "s": False, "w": False}
        for d in DIR_FULL:
            if not self.blocked[d]:
                if self.locked[d]:
                    dirs.append(DIR_FULL[d]+" (locked)")
                else:
                    dirs.append(DIR_FULL[d])
            n = DIR_FULL[d]+" - "+str(self.mineprog[d])+"%"
            if self.resources[d] and self.mined[d] >= 0:
                n += " ("+self.resources[d]+")"
            nirs.append(n)
        msg += ", ".join(dirs)
        if not dgn:
            if self.z > 0:
                msg += "\nMining progress: "+", ".join(nirs)
            else:
                msg += "\nTrees: " + \
                    str(self.stability)+"\nChopping progress: " + \
                    str(self.mineprog["w"])+"%"
        if len(self.special) > 0:
            msg += "\n\nLandmarks here: "+", ".join(self.special)
        if "Road" in self.special or "Paved Road" in self.special:
            roadirs = []
            for d in DIR_FULL:
                if ("Road" in self.get_border(d).special or "Paved Road" in self.get_border(d).special) and not self.blocked[d]:
                    roadirs.append(DIR_FULL[d])
            if len(roadirs) > 0:
                msg += "\nRoad directions: "+", ".join(roadirs)
            else:
                msg += "\nThe road doesn't lead anywhere."
        msg += "\n\nKobolds here:\n"
        ks = []
        cs = []
        for k in self.world.kobold_list:
            if k.get_place() == self:
                ks.append(k.display())
                if k.party:
                    for c in k.party.c_members:
                        if c.display() not in cs:
                            cs.append(c.display())
        msg += ", ".join(ks)
        if len(cs) > 0:
            msg += "\nTamed creatures here:\n"+", ".join(cs)
        msg += "\n\nItems here:\n"
        ks = []
        for i in self.items:
            ks.append(i.display())
        msg += ", ".join(ks)
        thing = self.get_tribe()
        if thing:
            msg += "\n\nThe "+thing.name+" den is here."
        elif self.camp:
            if self.camp.get("magic", False):
                cn = "Tiny Hut"
            else:
                cn = "camp"
            if self.camp["tribe"]:
                msg += "\n\nA "+cn+" was made here by " + \
                    self.camp["tribe"].name+"."
            else:
                msg += "\n\nA "+cn+" was made here by a rogue kobold."
            msg += "\nHeat: " + \
                str(self.camp["heat"])+"\nDefense: "+str(self.camp["defense"])
            msg += "\nSpace (in use/available): " + \
                str(self.space_in_use)+"/"+str(self.camp["defense"]+5)
            watch = []
            wdef = 0
            for k in self.camp["watch"]:
                mystr = k.watch_strength()
                wdef += mystr
                watch.append(k.display()+" (Defense: "+str(mystr)+")")
            msg += "\nWatchmen (+"+str(wdef)+" Defense):\n"+", ".join(watch)
        action_queue.append(["embed", me.get_chan(), discord.Embed(
            type="rich", title=title, description=msg)])
        return msg
