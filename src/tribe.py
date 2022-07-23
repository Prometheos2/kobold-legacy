import math
import os
import random
import time
from typing import Iterable

import discord

from creature import Creature
from tile import Tile

from ..kobold import COLOR_STAT
from ..kobold import DIR_FULL
from ..kobold import OPP_DIR
from ..kobold import Kobold
from ..kobold import building_data
from ..kobold import check_req
from ..kobold import choice
from ..kobold import console_print
from ..kobold import consume_item
from ..kobold import find_building
from ..kobold import find_research
from ..kobold import game_print
from ..kobold import has_item
from ..kobold import landmark_data
from ..kobold import research_data
from ..kobold import spawn_item


def tribe_name() -> str:
    try:
        path = os.path.join("data", "tribe_names.txt")
        f = open(path)
    except BaseException:
        console_print('ERROR: Cannot find tribe name list')
        return "Erroneously-named Tribe"
    temp_names = []
    for line in f:
        nam = line.strip('\n')
        nam = nam.capitalize()
        temp_names.append(nam)
    f.close()
    return choice(temp_names) + " " + choice(temp_names)


class Tribe:
    def __init__(self, world, x=None, y=None, z=1):
        self.name = tribe_name()
        self.world = world
        self.space = 15
        self.month = 1
        self.heat_faction = {"Goblin": 1}
        self.shc_faction = {"Goblin": 1}
        self.watchmen = []
        self.chieftain = None
        self.overseer = None
        self.fo = []
        self.z = z
        self.water = 50
        self.water_max = 50
        self.wpm = 10
        self.gift = 0
        self.invites = []
        self.tavern = []
        self.tavern_open = True
        self.banned = []
        self.prison = []
        self.kennel = []
        self.kennel_items = []
        self.tasks = []
        if x is not None and y is not None:  # tribe created by a player mid-game
            self.x = x
            self.y = y
        elif "0,0,1" not in self.world.map:
            self.x = 0
            self.y = 0
            self.world.map["0,0,1"] = Tile(self.world, 0, 0, 1)
            self.world.map["0,0,1"].stability = 110
        else:
            tile = self.world.find_distant_tile()
            (self.x, self.y) = (tile.x, tile.y)
            tile.stability = 110
        if x is None or y is None:  # ensure that we don't get a den with all four tunnels blocked
            p = world.get_tile(self.x, self.y, self.z)
            d = choice(list(OPP_DIR.keys()))
            p.blocked[d] = False
            op = p.get_border(d)
            op.blocked[OPP_DIR[d]] = False
        self.kobolds = []
        self.items = []
        self.graveyard = {}
        self.research = []
        self.buildings = []
        self.building_health = {}
        self.research_prog = {}
        self.building_prog = {}
        self.research_relay = {}
        self.building_relay = {}
        self.goblins_neutral = False
        global action_queue
        self.id = self.world.tid
        self.world.tid += 1
        self.dom_prog = {}
        self.farmable = ["Raw Mushroom"]
        action_queue.append(["newchan", "tribe-"+str(self.id)+"-log"])
        action_queue.append(["newchan", "tribe-"+str(self.id)+"-chat"])
        if x is None and y is None:  # initialize starting items and kobolds, if game-generated
            gc = self.world.find_distant_tile(random.randint(10, 15))
            gc.special = ["Goblin Camp"]
            spawn_item("Ration", self, 6)
            spawn_item("Stone Chunk", self, 5)
            spawn_item("Bones", self, 5)
            hasmale = False
            hasfemale = False
            for x in COLOR_STAT:
                k = Kobold(self)
                self.add_bold(k)
                k.random_stats(x)
                k.hp = k.max_hp
                k.cp = k.max_cp
                if k.male:
                    hasmale = True
                else:
                    hasfemale = True
            if not hasmale:
                choice(self.kobolds).male = True
            if not hasfemale:
                choice(self.kobolds).male = False
        toremove = []
        for e in world.encounters:
            if e.place.x == self.x and e.place.y == self.y and e.place.z == self.z:
                toremove.append(e)
        for e in toremove:
            world.encounters.remove(e)

    @property
    def space_in_use(self):
        sp = len(self.kobolds)
        for k in self.tavern:
            if k.party or k.nick:
                sp += 1
        sp = max(sp-self.buildings.count("Bunk Beds"), math.ceil(sp/2))
        csp = 0
        for c in self.kennel:
            csp += c.corpse["size"]
        sp += math.floor(csp/2)
        return sp

    @property
    def defense(self):
        d = 0
        for b in self.buildings:
            res = find_building(b)
            if res.get("defense", 0) > 0:
                if b not in self.building_health or self.building_health[b] >= 50:
                    d += res["defense"]
        return d

    def building_damage(self, build, dmg):
        if build not in self.building_health:
            self.building_health[build] = 100
        if self.building_health[build]-dmg < 0:
            game_print(build+" was destroyed!", self.get_chan())
            self.unfinish_building(find_building(build))
            return
        elif self.building_health[build] >= 50 and self.building_health[build]-dmg < 50:
            game_print(build+" took "+str(dmg) +
                       "% damage. It needs repair to be functional again.", self.get_chan())
        else:
            game_print(build+" took "+str(dmg)+"% damage.", self.get_chan())
        self.building_health[build] -= dmg

    def has_building(self, build):
        has = False
        for b in self.buildings:
            if b not in self.building_health or self.building_health[b] > 50:
                if b == build:
                    has = True
                elif find_building(b).get("counts_as", "none") == build:
                    has = True
        return has

    def get_population(self):
        p = 0
        l = 0
        n = 0
        for k in self.world.kobold_list:
            if k.tribe == self:
                p += 1
                if k.has_trait("locked"):
                    l += 1
                if k.nick:
                    n += 1
        return (p, l, n)

    def get_chan(self):
        return "tribe-"+str(self.id)+"-log"

    def add_bold(self, k):
        if isinstance(k, Kobold) and k not in self.kobolds:
            self.kobolds.append(k)

    def examine(self, me):
        title = self.name+", Month "+str(self.month)
        msg = "Time until month change: "
        sec = me.world.next_mc_time-time.time()
        if sec > 0:
            h = int(math.floor(float(sec/3600)))
            m = int(math.floor(float((sec % 3600)/60)))
            s = int(sec % 60)
            msg += str(h)+"h, "+str(m)+"m, "+str(s)+"s\n\n"
        else:
            msg += "Any moment now...\n\n"
        if self.has_building("Reservoir"):
            msg += "Water: "+str(self.water)+"/" + \
                str(self.water_max)+" (+"+str(self.wpm)+"/month)\n"
        msg += "Space (in use/available): " + \
            str(self.space_in_use)+"/"+str(self.space)+"\n"
        msg += "Base Defense: "+str(self.defense)+"\nHeat: "
        heats = []
        for f in self.heat_faction:
            heats.append(f+": %.1f" % round(self.heat_faction[f], 1))
        msg += ", ".join(heats)+"\nWatchmen: "
        watch = []
        wdef = 0
        for k in self.watchmen:
            mystr = k.watch_strength()
            wdef += mystr
            watch.append(k.display()+" (Defense: "+str(mystr)+")")
        msg += "+"+str(wdef)+" defense"
        if len(watch) > 0:
            msg += "\n"+", ".join(watch)
        builds = {}
        for b in self.buildings:
            if b not in builds:
                builds[b] = 1
            else:
                builds[b] += 1
        buildlist = []
        for b in builds:
            bb = b
            if builds[b] > 1:
                bb += " x"+str(builds[b])
            if b in self.building_health:
                bb += " ("+str(self.building_health[b])+"%)"
            buildlist.append(bb)
        msg += "\n\nBuildings: "+", ".join(buildlist)
        builds = {}
        for b in self.research:
            if b not in builds:
                builds[b] = 1
            else:
                builds[b] += 1
        buildlist = []
        for b in builds:
            if builds[b] > 1:
                buildlist.append(b+" x"+str(builds[b]))
            else:
                buildlist.append(b)
        msg += "\n\nResearch done: "+", ".join(buildlist)
        t = self.world.get_tile(self.x, self.y, self.z)
        nirs = []
        for d in DIR_FULL:
            n = DIR_FULL[d]+" - "+str(t.mineprog[d])+"%"
            if t.resources[d] and t.mined[d] >= 0:
                n += " ("+t.resources[d]+")"
            nirs.append(n)
        msg += "\n\nMining progress: "+", ".join(nirs)
        action_queue.append(["embed", me.get_chan(), discord.Embed(
            type="rich", title=title, description=msg)])
        return msg

    def destroy(self):
        tile = self.world.get_tile(self.x, self.y, self.z)
        console_print("Tribe "+str(self.id)+" destroyed.")
        movers = list(self.items)
        for x in movers:
            if random.randint(1, 4) == 4:
                x.move(tile)
            else:
                x.destroy("Den abandoned")
        tile.special.append("Ruined Den")
        self.world.tribes.remove(self)
        action_queue.append(
            ["delchan", "tribe-"+str(self.id)+"-log", time.time()+600])
        action_queue.append(
            ["delchan", "tribe-"+str(self.id)+"-chat", time.time()+600])

    def get_available_research(self, k=None):
        ar = []
        for r in research_data:
            good = "good"
            if r["name"] in self.research and not r.get("repeatable", False):
                good = False
            if good:
                g = check_req(self, r.get("req", []), k)
                if g != "good":
                    good = False
            if good:
                ar.append(r["name"])
        return ar

    def get_available_builds(self, k=None):
        ar = []
        for r in building_data:
            good = True
            if r["name"] in self.buildings and not r.get("repeatable", False):
                good = False
            if r.get("landmark", False) and r["name"] in self.world.get_tile(self.x, self.y, self.z).special and not r.get("repeatable", False):
                good = False
            if r.get("space", 0) > self.space:
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
                g = check_req(self, r.get("req", []), k)
                if g != "good":
                    good = False
            if good:
                ar.append(r["name"])
        return ar

    def do_research(self, k, res):
        base = (k.smod("int")+(k.skmod("research")*3))+10
        if k.tribe.has_building("Research Lab"):
            prog = math.floor(base*1.75)
        else:
            prog = random.randint(base, math.floor(base*1.5))
        prog += k.equip_bonus("research")
        r = res["name"]
        if r not in self.research_relay:
            self.research_relay[r] = {}
        if str(k.id) not in self.research_relay[r]:
            self.research_relay[r][str(k.id)] = 0
        relays = 10
        for a in self.research_relay[r]:
            if a == str(k.id):
                continue
            relays += self.research_relay[r][a]
        prog = int(prog*(1-(self.research_relay[r][str(k.id)]/relays)))
        self.research_relay[r][str(k.id)] += 1
        prog = max(1, prog)
        if r not in self.research_prog:
            self.research_prog[r] = 0
        exp = prog
        if k.familiar(r) > 0:
            prog *= 2
        self.research_prog[r] += prog
        diff = res["diff"]
        if res.get("repeatable", False):
            diff += int((self.research.count(r)**1.5)*res["diff"])
        k.p("[n] has made "+str(prog)+" progress researching " +
            r+". ("+str(self.research_prog[r])+"/"+str(diff)+")")
        if self.research_prog[r] >= diff:
            k.p("[n] has finished the research for "+r+"!")
            self.finish_research(res)
            exp += min(prog*4, diff/4)
        k.gain_xp("research", exp)
        k.get_familiar(r, exp)

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
            self.finish_building(res)
            exp += min(prog*4, res["work"]/4)
        k.gain_xp("construction", exp)
        k.gain_fam(res.get("req", []), prog)

    def finish_research(self, res):
        self.research.append(res["name"])
        self.justbuilt = res["name"]
        if res["name"] == "Cultural Expansion":
            for f in ["Goblin", "Human", "Elf", "Dwarf"]:
                if f in self.heat_faction and self.heat_faction[f] > 0:
                    self.heat_faction[f] = max(
                        1, self.heat_faction[f]-(5+self.research.count(res["name"])))
        del self.research_prog[res["name"]]

    def finish_building(self, res):
        self.buildings.append(res["name"])
        self.justbuilt = res["name"]
        self.building_prog[res["name"]] = 0
        self.space -= res.get("space", 0)
        if res.get("heat", 0) != 0:
            for f in ["Goblin", "Human", "Elf", "Dwarf"]:
                if f in self.heat_faction and self.heat_faction[f] > 0:
                    if res["heat"] < 0:
                        self.heat_faction[f] = max(
                            1, self.heat_faction[f]+(res["heat"]))
                    else:
                        self.heat_faction[f] += res["heat"]
        needs = res.get("materials", [])
        for n in needs:
            gra = n.split("/")
            for b in gra:
                arg = b.split(":")
                if len(arg) == 1:
                    arg.append(1)
                if self.has_item(arg[0], int(arg[1])):
                    self.consume_item(arg[0], int(arg[1]))
                    break
                else:
                    console_print("Could not consume "+b +
                                  " when building "+res["name"]+".", True)
        if res["name"] == "Reservoir":
            self.water_max += 25
        if " Farm" in res["name"]:  # silly but effective fix for "farm fencing" resetting cap
            t = self.world.get_tile(self.x, self.y, self.z)
            t.farm_cap = 200

    def unfinish_building(self, res):
        if res["name"] in self.buildings:
            self.buildings.remove(res["name"])
        if res["name"] in self.building_health:
            del self.building_health[res["name"]]
        self.space += res.get("space", 0)
        if res.get("heat", 0) != 0:
            for f in ["Goblin", "Human", "Elf", "Dwarf"]:
                if f in self.heat_faction:
                    self.heat_faction[f] -= res["heat"]
        if res["name"] == "Reservoir":
            self.water_max -= 25
            if self.water > self.water_max:
                self.water = self.water_max

    def community_effort(self):
        celist = self.get_available_research()+self.get_available_builds()
        tally = {}
        console_print("now tallying votes for CE")
        for k in self.kobolds:
            if k.ce in celist:
                if k.ce in tally:
                    tally[k.ce] += 1
                else:
                    tally[k.ce] = 1
        if len(tally) <= 0:
            console_print("community effort failed: no votes")
            return  # no kobolds voting
        best = None
        ties = []
        for x in tally:
            if not best or tally[x] > tally[best]:
                best = x
        for x in tally:
            if tally[x] == tally[best]:
                ties.append(x)
        if len(ties) <= 0:
            console_print("community effort failed: unable to tally ties")
            return  # probably won't happen but just in case
        ce = choice(ties)
        thing = find_building(ce)
        res = False
        if not thing:
            thing = find_research(ce)
            res = True
        prog = 0
        for k in self.kobolds:
            if res:
                prog += max(1, k.smod("str")+k.skmod("construction")+5)
            else:
                prog += max(1, k.smod("int")+k.skmod("research")+5)
            prog += k.ap*5
            k.ce = ""
        game_print("The community has made "+str(prog) +
                   " progress toward "+thing["name"]+".", self.get_chan())
        if res:
            if thing["name"] not in self.research_prog:
                self.research_prog[thing["name"]] = 0
            self.research_prog[thing["name"]] += prog
            diff = thing["diff"]
            if thing.get("repeatable", False):
                diff += int((self.research.count(
                    thing["name"])**1.5)*thing["diff"])
            if self.research_prog[thing["name"]] >= diff:
                self.finish_research(thing)
        else:
            if thing.get("landmark", False):
                tile = self.world.get_tile(self.x, self.y, self.z)
                if thing["name"] not in tile.building_prog:
                    tile.building_prog[thing["name"]] = 0
                tile.building_prog[thing["name"]] += prog
                if tile.building_prog[thing["name"]] >= thing["work"]:
                    tile.finish_building(thing, k)
            else:
                if thing["name"] not in self.building_prog:
                    self.building_prog[thing["name"]] = 0
                self.building_prog[thing["name"]] += prog
                if self.building_prog[thing["name"]] >= thing["work"]:
                    self.finish_building(thing)

    def election(t):
        tally = {}
        for k in t.kobolds:
            if k.age < 6 or not k.nick or k.vote < 0:
                continue
            bad = False
            for j in t.kobolds:
                if j.id == k.vote and j.has_trait("inactive"):
                    bad = True
            if bad:
                continue
            v = str(k.vote)
            if v in tally:
                tally[v] += 1
            else:
                tally[v] = 1
        if len(tally) <= 0:
            return  # no kobolds voting
        best = None
        ties = 0
        for x in tally:
            if not best or tally[x] > tally[best]:
                best = x
        for x in tally:
            if tally[x] == tally[best]:
                ties += 1
        console_print("election time. best="+str(best)+", ties="+str(ties))
        if ties == 1 and int(best) != -1:
            for k in t.kobolds:
                if k.id == int(best) and t.chieftain != k:
                    game_print("The people have spoken. "+k.display() +
                               " will be our new Chieftain.", t.get_chan())
                    if t.chieftain:
                        action_queue.append(
                            ["delrole", "Chieftain", t.chieftain.d_user_id])
                    t.chieftain = k
                    action_queue.append(["addrole", "Chieftain", k.d_user_id])
                    if t.overseer == k:
                        t.overseer = None

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

    def gain_heat(self, h, faction=None):
        if not faction:
            fs = ["Goblin", "Human", "Elf", "Dwarf"]
        else:
            fs = [faction]
        for f in fs:
            if f not in self.shc_faction:
                self.shc_faction[f] = 1
            if f not in self.heat_faction:
                if faction:
                    self.heat_faction[faction] = 0
                else:
                    continue
            console_print("Tribe "+str(self.id)+" gains "+str(h)+" "+f+" heat")
            if self.heat_faction[f]+h <= self.shc_faction[f]:
                self.heat_faction[f] += h
                #console_print("Adding raw heat now "+str(self.heat_faction[faction]))
                continue
            elif self.heat_faction[f] <= self.shc_faction[f]:
                h -= self.shc_faction[f]-self.heat_faction[f]
                self.heat_faction[f] = self.shc_faction[f]
            self.heat_faction[f] += h/5
            #console_print("Adding capped heat now "+str(self.heat_faction[faction]))

    def violate_truce(self, k, f):
        k.p("This violates the tribe's truce with the "+f +
            " faction. This betrayal will not easily be forgotten.")
        self.shc_faction[f] = abs(self.shc_faction[f])
        self.heat_faction[f] = max(
            self.heat_faction[f], int(self.shc_faction[f]/2))

    def invasion(t, faction="Goblin"):
        invasion = int(t.heat_faction[faction]*random.randint(80, 120)/100)
        game_print("A raid consisting of "+str(invasion)+" " +
                   faction+" invaders attacks!", t.get_chan())
        if faction == "Human":
            builds = []
            for b in t.buildings:
                r = find_building(b)
                if r.get("defense", 0) > 0 and r.get("destructible", True):
                    builds.append(b)
            siege = invasion
            if siege > 10 and len(builds) > 0:
                game_print(
                    "The humans fire a volley from their siege weaponry!", t.get_chan())
            while siege > 10 and len(builds) > 0:
                b = choice(builds)
                dmg = random.randint(10, siege)
                t.building_damage(b, dmg)
                siege -= dmg
                builds.remove(b)
        defense = t.defense
        if faction == "Ant":
            game_print(
                "The ants crawl all over the walls and ceiling, rendering our constructed defenses half as effective...", t.get_chan())
            defense = math.floor(defense/2)
        if faction == "Dwarf" and t.z > 0 and len(t.kobolds) > 0:
            tile = t.world.get_tile(t.x, t.y, t.z)
            game_print(
                "The cavern rumbles as dwarves tunnel into the vicinity from all directions...", t.get_chan())
            tile.stability -= random.randint(math.floor(invasion/4),
                                             math.floor(invasion/3))
            tile.cave_in(t.kobolds[0])
        dmg = 0
        dmgto = {}
        bolds = []
        for k in t.kobolds:
            if k.age >= 6 or not t.has_building("Nursery"):
                bolds.append(k)
        if t.space < t.space_in_use:
            outside = t.space_in_use-t.space
            game_print(
                "Some kobolds were caught sleeping outside! This wouldn't happen if we had enough space for everyone...", t.get_chan())
            for x in range(outside):
                k = choice(bolds)
                if k:
                    k.hp_tax(random.randint(1, invasion), "Slept in the open", dmgtype=choice(
                        ["bludgeoning", "slashing", "piercing"]))
                    bolds.remove(k)
        if invasion > defense and len(t.watchmen) > 0:
            dmg = invasion-defense
            game_print(
                "The invaders broke through our outer defenses. Our watchmen are the only thing between us and certain doom.", t.get_chan())
            for x in range(dmg):
                target = choice(t.watchmen)
                if isinstance(target, Creature):
                    tn = target.name
                else:
                    tn = str(target.id)
                if tn in dmgto:
                    dmgto[tn] += 1
                else:
                    dmgto[tn] = 1
                if faction == "Gnoll":
                    dmgto[tn] += 1
            wm = list(t.watchmen)
            for k in wm:
                defense += k.watch_damage(dmg, dmgto)
        if invasion > defense:
            game_print(
                "The invaders have breached our defenses and are running amok in the den!", t.get_chan())
            dmg = invasion-defense
            dmgto = {}
            targets = ["kobold", "building", "item"]
            builds = list(t.buildings)
            for b in building_data:
                if not b.get("destructible", True):
                    while b["name"] in builds:
                        builds.remove(b["name"])
            for x in range(dmg):
                hit = choice(targets)
                if hit == "building" and len(builds) > 0:
                    target = choice(builds)
                    t.building_damage(target, random.randint(1, 10))
                    if target not in t.buildings:
                        builds.remove(target)
                elif hit == "item" and len(t.items) > 0:
                    target = choice(t.items)
                    target.destroy("Lost in raid")
                    game_print(target.display() +
                               " was lost in the raid!", t.get_chan())
                elif len(bolds) > 0:
                    target = choice(bolds)
                    if str(target.id) in dmgto:
                        dmgto[str(target.id)] += 2
                    else:
                        dmgto[str(target.id)] = 2
                    if faction == "Gnoll":
                        dmgto[str(target.id)] += 2
            for k in bolds:
                if str(k.id) in dmgto:
                    k.hp_tax(dmgto[str(k.id)], "Civilian casualty", dmgtype=choice(
                        ["bludgeoning", "slashing", "piercing"]))
                if k.save("wis") < 12:
                    k.add_trait("stressed")
            game_print("The attack is finally over.", t.get_chan())
        else:
            game_print(
                "The invaders could not reach the den. We have made it through the raid.", t.get_chan())
        near = 0
        tils = t.world.scan(t, 3, False)
        for m in tils:
            if t.world.map[m] != t and (t.world.map[m].camp or t.world.map[m].get_tribe()):
                near += 1
        if faction == "Ant":
            t.gain_heat(5, faction)
        else:
            t.gain_heat(((len(t.kobolds)/2)+(t.month*2))*(1.1**near), faction)
        if t.has_building("Marble Statues") and faction in ["Goblin", "Human", "Elf", "Dwarf"] and t.heat_faction[faction] > 5:
            t.heat_faction[faction] -= 5
        t.shc_faction[faction] *= 2


    def check_req_4tribes(self, req: Iterable[str]) -> str:

        good = "good"
        tile = self.world.get_tile(self.x, self.y, self.z)

        for q in req:
            req_category = q[0]
            req_objects = q[1]

            if req_category == "research":
                if req_objects in self.research:
                    continue

                good = "Research missing: " + req_objects

            elif req_category == "item":
                if self.has_item(req_objects):
                    good = "good"
                    continue

                good = "Item missing: " + req_objects

            elif req_category == "tool":
                g = "Tool missing: " + req_objects
                for i in self.items:
                    if i.tool == req_objects:
                        g = "good"
                        break
                if good == "good":
                    good = g

            elif req_category == "building":
                if not self.has_building(req_objects):
                    good = "Building missing: " + req_objects

            elif req_category == "landmark":
                if req_objects not in tile.special:
                    good = "Landmark missing: " + req_objects
            elif req_category == "minlevel":
                if req_objects > self.z:
                    good = "Must be done at level " + str(
                        req_objects) + " or lower."
            elif req_category == "maxlevel":
                if req_objects < self.z:
                    good = "Must be done at level " + str(
                        req_objects) + " or lower."
            elif req_category == "tribe":
                if not req_objects:
                    good = "You cannot do that in a tile with a den."
                    continue
                good = "Must be done in a tile with a den."
            elif req_category == "liquid":
                g = "Liquid source missing: " + req_objects
                for l in tile.special:
                    if landmark_data[l].get("liquid_source",
                                            "none") == req_objects:
                        g = "good"
                if good == "good":
                    good = g
        return good
