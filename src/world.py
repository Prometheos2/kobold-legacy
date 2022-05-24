import math
import random
import time

from ..kobold import (Kobold, Tile, Tribe, chance, choice, console_print,
                      find_building, forage, game_print, get_tri_distance,
                      item_cats, item_data, landmark_data, liquid_data,
                      skill_data, spawn_item, trait_data)


class World:
    def __init__(self):
        self.tribes = []
        self.map = {}
        self.kobold_list = []
        self.kid = 0
        self.tid = 0
        self.pid = 0
        self.did = 0
        self.month = 1
        self.encounters = []
        self.dungeons = []
        t = time.gmtime()
        self.next_mc_time = time.time(
        )-(t[5]+(t[4]*60)+((t[3] % 24)*3600))+86400

    def get_tile(self, x, y, z, gen=True):
        c = ",".join([str(x), str(y), str(z)])
        if c in self.map:
            return self.map[c]
        elif gen:
            self.map[c] = Tile(self, x, y, z)
            return self.map[c]
        return None

    def find_distant_tile(self, dist=10, z=1):
        edges = {"lowx": 0, "lowy": 0, "highx": 0, "highy": 0}
        for t in self.tribes:
            if t.x < edges["lowx"]:
                edges["lowx"] = t.x
            elif t.x > edges["highx"]:
                edges["highx"] = t.x
            if t.y < edges["lowy"]:
                edges["lowy"] = t.y
            elif t.y > edges["highy"]:
                edges["highy"] = t.y
        edge = choice(["lowx", "lowy", "highx", "highy"])
        if "low" in edge:
            edges[edge] -= dist
        else:
            edges[edge] += dist
        if "x" in edge:
            x = edges[edge]
            y = random.randint(edges["lowy"], edges["highy"])
            if edges["lowy"] == edges["highy"]:
                a = random.randint((dist-1)*-1, dist-1)
                if "low" in edge:
                    x += abs(a)
                else:
                    x -= abs(a)
                y += a
        else:
            y = edges[edge]
            x = random.randint(edges["lowx"], edges["highx"])
            if edges["lowx"] == edges["highx"]:
                a = random.randint((dist-1)*-1, dist-1)
                if "low" in edge:
                    y += abs(a)
                else:
                    y -= abs(a)
                x += a
        maploc = str(x)+","+str(y)+","+str(z)
        console_print("distant tile found: "+maploc)
        if maploc not in self.map:
            self.map[maploc] = Tile(self, x, y, z)
        return self.map[maploc]

    def find_tile_feature(self, dist, place, thing, feature, gen=False):
        closest = dist
        ct = None
        coords = self.scan(place, dist, gen)
        for m in coords:
            if feature == "resources":
                search = []
                for d in self.map[m].resources:
                    search.append(self.map[m].resources[d])
            elif feature == "factionbase":
                search = []
                for l in self.map[m].special:
                    if landmark_data[l].get("faction", None):
                        search.append(l)
                        thing = l
            else:
                search = getattr(self.map[m], feature, [])
            if thing in search:
                h = abs(self.map[m].x-place.x)
                v = abs(self.map[m].y-place.y)
                console_print("searching "+m+"; h is "+str(h)+" v is " +
                              str(v)+" while closest is "+str(closest), lp=True)
                if h+v < closest:
                    closest = h+v
                    ct = self.map[m]
                    console_print("this is closer", lp=True)
        if ct:
            console_print("Found a "+str(thing)+" at "+str((ct.x, ct.y, ct.z)))
        else:
            console_print("No "+str(thing)+" found within "+str(dist)+" tiles")
        return ct

    def scan(self, origin, dist, gen):
        global console_crosspost
        console_print("Scanning from "+str((origin.x, origin.y)) +
                      " with distance "+str(dist))
        nope = False
        if console_crosspost:
            console_crosspost = False
        else:
            nope = True
        coords = []
        for x in range(origin.x-dist, origin.x+dist):
            for y in range(origin.y-dist, origin.y+dist):
                if get_tri_distance(origin.x, origin.y, x, y) > dist:
                    continue
                t = self.get_tile(x, y, origin.z, gen)
                if t:
                    coords.append(str(x)+","+str(y)+","+str(origin.z))
        if not nope:
            console_crosspost = True
        return coords

    def month_change(self):
        global console_crosspost
        eggs = []
        spoiling = []
        contained = []
        creatures = []
        diseases = []
        for t in trait_data:
            if trait_data[t].get("mc_disease", False):
                diseases.append(t)
        console_crosspost = False
        console_print("Pruning encounters", True)
        toremove = []
        for e in self.encounters:
            if chance(20):
                # some encounters despawn so that the world isn't abosolutely flooded with encounters after a few months
                toremove.append(e)
            elif len(e.creatures) <= 0:
                toremove.append(e)  # despawn if there's nothing here lol
            elif isinstance(e.creatures[0], Kobold):
                # despawn wanderers so they don't leave corpses or ghost encounters
                toremove.append(e)
        for x in toremove:
            crs = list(x.creatures)
            for c in crs:
                if c in self.kobold_list:
                    c.despawn()
            if x in self.encounters:
                self.encounters.remove(x)
        # so new births/spawns this month are not processed in the same month
        klist = list(self.kobold_list)
        console_print("Processing tribe upkeep", True)
        for t in self.tribes:
            liqs = 0
            tav = list(t.tavern)
            game_print("📌**It is now month " +
                       str(t.month+1)+".**", t.get_chan())
            for k in tav:
                if not k.tribe and not k.party and not k.nick:
                    k.despawn()  # should get MOST edge cases
            for i in list(t.items+t.kennel_items):
                if i.type == "egg":
                    eggs.append(i)
                if i.perishable:
                    spoiling.append(i)
                if i.liquid and i.liquid != "Water" and not liquid_data[i.liquid].get("potion", False) and liquid_data[i.liquid].get("drinkable", True):
                    liqs += i.liquid_units
                if i.inert:
                    i.inert = False
                if hasattr(i, "contains") and i.contains and chance(50):
                    contained.append(i.contains)
            for f in t.heat_faction:
                if t.heat_faction[f] > 0:
                    if f in t.shc_faction and t.shc_faction[f] < 1:
                        t.shc_faction[f] = 1
                        game_print(
                            "The "+f+" truce has expired, apparently.", t.get_chan())
                    if f not in t.shc_faction:
                        t.shc_faction[f] = 1
                    t.invasion(f)
            builds = list(t.buildings)
            for b in builds:
                build = find_building(b)
                if build.get("temporary", False):
                    t.unfinish_building(build)
            t.watchmen = []
            prs = list(t.prison)
            if len(prs) > 0 and not t.has_building("Prison"):
                game_print(
                    "Without a prison to contain them, the prisoners are able to slip away before anyone notices. We're never seeing them again...", t.get_chan())
                for k in prs:
                    k.despawn()
            if t.has_building("Tavern"):
                customers = math.floor((math.sqrt((8*liqs)+1)-1)/2)
                for x in range(customers):
                    k = Kobold(t)
                    k.tribe = None
                    k.random_stats()
                    (k.x, k.y, k.z) = (t.x, t.y, t.z)
                    t.tavern.append(k)
                    if chance(50):
                        k.add_trait("trader")
                        k.get_wares(liqs*5)
            if len(t.kennel) > 0 and not t.has_building("Kennel"):
                game_print(
                    "Without a kennel to contain them, we aren't able to keep our animals from wandering off...", t.get_chan())
                t.kennel = []
            for c in t.kennel:
                if c not in creatures:
                    creatures.append(c)
            t.community_effort()
            t.election()
            t.building_relay = {}
            t.research_relay = {}
            t.month += 1
            if t.gift != 0:
                t.gift = 0
            t.water += t.wpm
            if t.water >= t.water_max:
                t.water = t.water_max
        console_print("Processing map tiles", True)
        for m in self.map:
            t = self.map[m]
            for i in t.items:
                if i.type == "egg" and t.camp:
                    eggs.append(i)  # eggs can hatch in safety
                if (i.type == "egg" and not t.camp) or i.perishable:
                    spoiling.append(i)  # eggs cannot hatch out of safety
                if i.inert:
                    i.inert = False
                if hasattr(i, "contains") and i.contains and chance(50):
                    contained.append(i.contains)
            for c in t.pasture:
                if c not in creatures:
                    creatures.append(c)
            farmed = []
            prog_cap = t.farm_cap
            for f in t.farming_prog:
                for i in item_data:
                    if i["name"] == f:
                        break
                shrooms = math.floor(
                    min(prog_cap, t.farming_prog[f])/i["farming"]["prog"])
                prog_cap -= shrooms*i["farming"]["prog"]
                if shrooms > 0:
                    spawn_item(f, t, shrooms)
                    farmed.append(str(shrooms)+" "+f)
            if len(farmed) > 0:
                game_print("This month's harvest yields: " +
                           "; ".join(farmed)+".", t.get_chan())
            t.invasion()
            if not t.get_tribe() and not t.camp:
                l = choice(t.special)
                if l and landmark_data[l].get("spawns", None) and chance(landmark_data[l].get("spawn_chance", 100)):
                    t.spawn_encounter(force=choice(landmark_data[l]["spawns"]))
                elif chance(33):
                    t.spawn_encounter()
            if t.z == 0 and t.stability < 10:
                t.stability += random.randint(0, t.stability)
            t.farming_prog = {}
        tribolds = {}
        console_print("Processing kobold upkeep", True)
        slist = list(klist)
        for k in slist:
            if k.has_trait("starving") and k in klist:
                klist.remove(k)
                klist.insert(0, k)
        for k in klist:
            if k not in self.kobold_list:
                continue
            if k.dungeon:
                k.die("Caught in a dungeon")
                continue
            k.searched = []
            k.spartners = []
            if k.party:
                for c in k.party.c_members:
                    if c not in creatures:
                        creatures.append(c)
            for i in k.items:
                if i.type == "egg":
                    eggs.append(i)
                if i.perishable:
                    spoiling.append(i)
                if i.inert:
                    i.inert = False
                if hasattr(i, "contains") and i.contains and chance(50):
                    contained.append(i.contains)
            if not k.has_trait("fasting") and not k.has_trait("fed"):
                k.auto_eat()
            trs = list(k.traits)
            for t in trs:
                if trait_data[t].get("mc_save_to_cure", False):
                    if k.save(trait_data[t]["save_stat"])+k.ap >= trait_data[t]["save"]:
                        k.del_trait(t)
                        k.p("[n] has overcome their " +
                            trait_data[t].get("display", t)+" condition.")
                        continue
                if trait_data[t].get("mc_lethal", False):
                    k.die("Succumbed to "+trait_data[t].get("display", t))
                    break
                if trait_data[t].get("mc_change", None):
                    k.del_trait(t)
                    k.add_trait(trait_data[t]["mc_change"])
                    if trait_data[trait_data[t]["mc_change"]].get("visible", False):
                        k.p("[n] has developed: "+trait_data[trait_data[t]
                            ["mc_change"]].get("display", t))
            if k not in self.kobold_list:
                continue
            if k.age < 3 and chance(50):
                forage(k)
            if k.age < 6:
                k.age_up()  # child stat growth
            k.age += 1
            if k.nick:
                k.monthsnamed += 1
            k.booze_ap = 0
            if len(k.spells) > 0:
                k.mp_gain(math.ceil(k.max_mp/2))
            for a in list(k.traits):
                if trait_data[a].get("mc_reset", False):
                    k.del_trait(a)
            if not k.has_trait("fed"):
                if k.has_trait("starving"):
                    k.die("Starvation")
                else:
                    k.add_trait("starving")
                    if len(k.eggs) > 0:
                        k.p("Disaster... the eggs [n] was expecting never came...")
                    if not k.has_trait("stressed") and k.save("wis") < 12 and chance(50):
                        k.add_trait("stressed")
            else:
                k.hp_gain(1+math.ceil(k.skmod("resilience")/2))
                if len(k.eggs) > 0:
                    for e in k.eggs:
                        egg = spawn_item("Kobold Egg", k)
                        egg.kobold = e
                    k.p("[n] lays "+str(len(k.eggs))+" healthy eggs!")
            k.eggs = []
            k.del_trait("fed")
            k.del_trait("fasting")
            dc = 15-k.smod("con")-k.skmod("vitality")
            place = k.get_place()
            if isinstance(place, Tribe):
                dc += max(0, 5-(place.space-place.space_in_use))
            if chance(max(1, dc)):
                dis = choice(diseases)
                if k.save(trait_data[dis].get("save_stat", "con"))+k.ap < trait_data[dis].get("save", 11):
                    k.add_trait(dis)
                    if trait_data[dis].get("visible", False):
                        k.p("[n] has developed: " +
                            trait_data[dis].get("display", t))
            k.hiding = 100
            for sk in skill_data:
                k.skillboost[sk] = 0
            k.ap = k.max_ap
            k.cp = k.max_cp
            if k.hp > 0 and k.tribe:
                if str(k.tribe.id) not in tribolds:
                    tribolds[str(k.tribe.id)] = 0
                tribolds[str(k.tribe.id)] += 1
                if k.nick and time.time()-k.lasttime >= 86400 and not k.has_trait("inactive"):
                    k.add_trait("inactive")
                    k.p("<@!"+str(k.d_user_id)+"> You have not submitted a command in the last 24 hours, so you are inactive. Anyone can now order you as though you were nameless. You can remove this status by submitting any command.")
                    if k.tribe.overseer == k:
                        k.tribe.overseer = None
                    if k.tribe.chieftain == k:
                        k.tribe.chieftain = None
                    k.vote = -1
        console_print("Processing creature upkeep", True)
        for c in creatures:
            c.searched = []
            for i in c.items:
                if i.type == "egg":
                    eggs.append(i)
                if i.perishable:
                    spoiling.append(i)
                if i.inert:
                    i.inert = False
                if hasattr(i, "contains") and i.contains and chance(50):
                    contained.append(i.contains)
            p = c.get_place()
            if not p:
                continue
            if not c.owner or c.owner.hp <= 0:
                newowners = []
                for k in klist:
                    if k.get_place() == p:
                        newowners.append(k)
                c.owner = choice(newowners)
                if c.owner:
                    game_print(c.display(
                    )+" senses that their master is not coming back and finds a new bond with "+c.owner.display()+".", c.get_chan())
            if p.z == 0 and "*grass" in c.diet:
                graze = True
            elif c.has_trait("fed"):
                graze = True
            else:
                graze = False
            if not graze:
                food = None
                fprio = 0
                area = list(c.items)+list(p.items)
                for i in area:
                    prio = 100-(i.ap*10)
                    skep = True
                    for d in c.diet:
                        cat = d.replace("*", "")
                        if cat not in item_cats:
                            continue
                        if i.name in item_cats[cat]:
                            skep = False
                    if skep:
                        continue
                    if i in spoiling:
                        prio += 100
                    if i.type == "bait":
                        prio += 100
                    if (i.type == "food" or i.type == "bait") and prio > fprio:
                        food = i
                        fprio = prio
                    elif i.type == "corpse" and "*meat" in c.diet:
                        food = i
                        fprio = 999
            if food or graze:
                if not graze:
                    food.num -= 1
                    if food.num <= 0:
                        food.destroy("Eaten by creature")
                c.hp_gain(1)
                if "domestic" in c.training and not isinstance(p, Tribe) and "Pasture" in p.special and "Egg" in c.products:
                    spawn_item("Egg", p)
            else:
                game_print(
                    c.display()+" was unable to find a meal and ran away...", c.get_chan())
                if c.party:
                    c.party.leave(c)
                if isinstance(p, Tribe):
                    if c in p.kennel:
                        p.kennel.remove(c)
                elif c in p.pasture:
                    p.pasture.remove(c)
            for a in list(c.traits):
                if trait_data[a].get("mc_reset", False):
                    c.del_trait(a)
        for c in contained:
            if c.perishable:
                spoiling.append(c)
        for e in eggs:
            e.hatch()
        for i in spoiling:
            i.destroy("Spoiled")
        console_crosspost = True
        tribes = list(self.tribes)
        for t in tribes:
            if str(t.id) not in tribolds or tribolds[str(t.id)] <= 0:
                t.destroy()
            else:
                console_print("Tribe "+str(t.id)+" has " +
                              str(tribolds[str(t.id)])+" left in the world")
        self.month += 1
