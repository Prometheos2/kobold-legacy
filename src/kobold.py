import math
import random
import time

import discord

from tribe import Tribe

from ..kobold import COLOR_STAT
from ..kobold import GENOME
from ..kobold import ROLENAMES
from ..kobold import STAT_COLOR
from ..kobold import STATS
from ..kobold import action_queue
from ..kobold import chance
from ..kobold import choice
from ..kobold import cmd_attack
from ..kobold import cmd_drop
from ..kobold import cmd_equip
from ..kobold import cmd_get
from ..kobold import console_print
from ..kobold import consume_item
from ..kobold import droll
from ..kobold import find_research
from ..kobold import game_print
from ..kobold import get_pdata
from ..kobold import has_item
from ..kobold import item_data
from ..kobold import liquid_data
from ..kobold import make_baby
from ..kobold import playerdata
from ..kobold import sandbox
from ..kobold import skill_data
from ..kobold import spawn_item
from ..kobold import spell_data
from ..kobold import trait_data


def kobold_name() -> str:
    vowels = ['a', 'i', 'o', 'u', 'e']
    penvowels = ['a', 'o', 'u', 'ay', 'ee', 'i']
    frontcluster = [
        'b', 'br', 'bl', 'd', 'dr', 'dl', 'st', 'str', 'stl', 'shl', 'k', 'p',
        'l', 'lr', 'sh', 'j', 'jr', 'thl', 'g', 'f', 'gl', 'gr', 'fl', 'fr',
        'x', 'z', 'zr', 'r'
    ]
    cluster = ['b', 'd', 'l', 'f', 'g', 'k', 'p', 'n', 'm', 's', 'v']
    fincluster = [
        'm', 'r', 'ng', 'b', 'rb', 'mb', 'g', 'lg', 'l', 'lb', 'lm', 'rg', 'k',
        'rk', 'lk', 'rv', 'v'
    ]
    finsyl = ['is', 'us', 'ex1', 'ex2', 'al', 'a', 'ex3']

    is_first_iter = True
    syl = random.randint(0, 2) + 1
    firstname = []
    vowel = choice(vowels)
    while syl > 0:
        if is_first_iter or syl == 1:
            if syl == 1:
                vowel = choice(penvowels)

            firstname.append(choice(frontcluster))
            is_first_iter = False
        else:
            firstname.append(choice(cluster))
        firstname.append(vowel)
        syl -= 1

    firstname.append(choice(fincluster))
    fin = choice(finsyl)
    if 'ex' not in fin:
        return "".join(firstname).capitalize()

    if vowel in ['o', 'ay', 'u', 'a']:
        if fin == 'ex1':
            firstname.append(choice(['er', 'ar']))
        elif fin == 'ex2':
            firstname.append(choice(['in', 'an']))
        elif fin == 'ex3':
            firstname.append('i')
    else:
        firstname.append(choice(['is', 'us', 'al', 'a']))

    return "".join(firstname).capitalize()

class Kobold:
    def __init__(self, tribe=None):
        self.name = kobold_name()
        self.nick = None
        self.orders = True
        self.emoji = None
        self.fo = []
        self.tribe = tribe
        self.familiarity = {}
        self.world = self.tribe.world
        self.id = self.world.kid
        self.world.kid += 1
        self.x = tribe.x
        self.y = tribe.y
        self.z = tribe.z
        self.d_user_id = None
        self.commandedby = None
        self.hiding = 100
        self.age = 12+random.randint(0, 24)
        self.monthsnamed = 0
        self.party = None
        self.carry = None
        self.breeders = []
        self.spartners = []
        self.children = []
        self.color = "brown"
        self.bio = "No description set."
        self.lastchief = None
        self.body = ["head", "horn", "horn", "eye",
                     "eye", "arm", "arm", "leg", "leg", "tail"]
        self.worns = {"body": None, "head": None, "acc": None}
        if chance(50):
            self.male = True
        else:
            self.male = False
        self.s = {}
        self.skill = {}
        self.skillboost = {}
        self.skillxp = {}
        self.eggs = []
        self.traits = []
        if chance(2):
            self.add_trait("nonbinary")
        self.items = []
        self.genome = {}
        self.didturn = False
        self.equip = None
        self.worn = None
        self.bound = None
        self.guardian = None
        for g in GENOME:
            self.genome[g] = [False, False]
        for st in STATS:
            self.s[st] = 0
        for sk in skill_data:
            self.skill[sk] = 0
            self.skillboost[sk] = 0
            self.skillxp[sk] = 0
        self.hp = self.max_hp
        self.mp = 0
        self.booze_ap = 0
        self.searched = []
        self.spells = []
        self.world.kobold_list.append(self)
        self.vote = -1
        self.ce = ""
        self.lastcommand = "none"
        self.stealthrolls = 0
        self.lastfollower = "none"
        self.lasttime = time.time()
        self.encounter = None
        self.parents = ["Unknown", "Unknown"]
        self.ap = self.max_ap
        self.cp = self.max_cp
        self.movement = 0
        self.dungeon = None

    @property
    def max_hp(self):
        st = 0
        for sk in self.skill:
            st += self.skill[sk]
        return max(1, self.s["con"]+self.skmod("resilience")+math.floor(st/5))

    @property
    def max_mp(self):
        if len(self.spells) > 0:
            return self.s["int"]+self.skmod("arcana")+self.skmod("sorcery")
        else:
            return 0

    @property
    def max_ap(self):
        ap = min(self.age*2, 10)
        for t in self.traits:
            if trait_data[t].get("max_ap", 0) != 0:
                ap += trait_data[t]["max_ap"]
        return max(0, ap)

    @property
    def max_cp(self):
        cp = self.s["cha"]+self.skmod("command")
        if self.tribe:
            if self.tribe.chieftain == self or self.tribe.overseer == self:
                cp *= 2
            p = self.tribe.get_population()
            if p[2] <= 1:
                cp *= 2
        return max(0, cp)

    @property
    def inv_size(self):
        if self.has_trait("trader"):
            return 10
        if self.hp <= 0:
            return -10
        inv = self.smod("str", False)+5
        for i in self.items:
            inv += i.inv_size
        if self.carry:
            inv -= 1
        return inv

    @property
    def ac(self):
        ac = self.smod("dex")+10
        for w in self.worns:
            if not self.worns[w]:
                continue
            if self.worns[w].heavy:
                ac = self.worns[w].ac+10
            else:
                ac += self.worns[w].ac
        for t in self.traits:
            ac += trait_data[t].get("ac", 0)
        return ac

    @property
    def shaded(self):
        if self.z != 0 or self.dungeon:
            return True
        elif self.has_trait("shade") or (self.equip and self.equip.name == "Silk Parasol"):
            return True
        else:
            for w in self.worn_items():
                if w.name in ["Sunglasses", "Outback Hat"]:
                    return True
            p = self.get_place()
            if isinstance(p, Tribe) and "Thatched Roof" in p.buildings:
                return True
            else:
                return False

    @property
    def stealth(self):
        st = self.smod("dex")+self.skmod("stealth")
        if self.has_trait("invisible"):
            st += 10
        elif self.has_trait("notrace"):
            st += 10
        return st

    def wearing_nonmage_equipment(self):
        if self.worns["body"] and not self.worns["body"].magic:
            return True
        return False

    def worn_items(self):
        i = []
        for w in self.worns:
            if self.worns[w]:
                i.append(self.worns[w])
        return i

    def familiar(self, r):
        res = find_research(r)
        if r in self.familiarity:
            fam = math.floor(self.familiarity[r]/res["diff"])
            #console_print(self.get_name()+" familiar with "+r+" = "+str(fam))
            return fam
        return 0

    def get_familiar(self, r, n):
        if r not in self.familiarity:
            self.familiarity[r] = 0
        oldfam = self.familiar(r)
        if oldfam >= 2:
            return  # nothing more to learn
        n += self.smod("int")*2
        self.familiarity[r] += n
        console_print(self.get_name()+" gained "+str(n)+" familiarity with "+r)
        newfam = self.familiar(r)
        if newfam > oldfam:
            if newfam >= 2:
                self.p("[n] has become very familiar with "+r+"!")
            else:
                self.p("[n] has become familiar with "+r+"!")

    def ap_gain(self, n, pr=True):
        self.ap += n
        if self.ap > self.max_ap:
            self.ap = self.max_ap
        if pr:
            self.p("[n] has gained "+str(n)+" AP.")

    def ap_tax(self, n):
        if n == 0:
            return True
        if self.ap >= n:
            self.ap -= n
            self.p("[n] spends "+str(n)+" AP (remaining: "+str(self.ap)+")")
            for t in self.traits:
                if trait_data[t].get("dmg_ap", 0) > 0:
                    self.hp_tax(
                        trait_data[t]["dmg_ap"]*n, trait_data[t].get("display", t), dmgtype="poison")
            return True
        else:
            self.p("[n] doesn't have enough AP. (need " +
                   str(n)+", have "+str(self.ap)+")")
        return False

    def stat_str(self, stat):
        st = self.s[stat]
        if st > 16 and (self.has_trait("inactive") or not self.nick):
            st = 16
        for t in self.traits:
            if stat in trait_data[t].get("stats", {}):
                st += trait_data[t]["stats"][stat]
        if not self.shaded:
            st = min(st, 10)
        ret = str(st)
        if st != self.s[stat]:
            ret = str(self.s[stat])+" ["+ret+"]"
        return ret

    def skill_str(self, skill):
        st = self.skmod(skill)
        ret = str(st)
        if st != self.skill[skill]:
            ret = str(self.skill[skill])+" ["+ret+"]"
        return ret

    def skmod(self, sk, rand=True):  # this is the KOBOLD skmod
        if sk not in self.skill:
            return 0
        ret = self.skill[sk]
        if ret > 5 and (self.has_trait("inactive") or not self.nick):
            ret = 5
        ret += self.skillboost[sk]
        for w in self.worn_items():
            if sk in w.skill_boost:
                ret += w.skill_boost[sk]
        return ret

    def smod(self, stat, rand=True):  # this is the KOBOLD smod
        st = self.s[stat]
        if st > 16 and (self.has_trait("inactive") or not self.nick):
            st = 16
        for t in self.traits:
            if stat in trait_data[t].get("stats", {}):
                st += trait_data[t]["stats"][stat]
        if stat == "dex":
            for w in self.worns:
                if self.worns[w] and self.worns[w].heavy:
                    st = min(st, 10)
        if rand:
            st += random.randint(0, 1)
        if not self.shaded:
            st = min(st, 10)
        return math.floor((st-10)/2)

    def save(self, stat):
        s = droll(1, 20)+self.smod(stat)
        if stat in ["str", "dex", "con"]:
            self.gain_xp("vitality", max(s+5, 5))
            s += random.randint(0, self.skmod("vitality"))
        else:
            self.gain_xp("willpower", max(s+5, 5))
            s += random.randint(0, self.skmod("willpower"))
        console_print(self.get_name()+" rolls a " +
                      stat+" save and gets "+str(s))
        return s

    def get_place(self):
        if hasattr(self, "dungeon") and self.dungeon:
            tile = self.dungeon.get_tile(self.x, self.y, self.z)
        else:
            tile = self.world.get_tile(self.x, self.y, self.z)
        if not tile:  # uh oh
            if self.dungeon:
                console_print(self.get_name()+" has no valid tile at "+str(
                    (self.x, self.y, self.z))+" in dungeon "+str(self.dungeon.id), True)
            else:
                console_print(self.get_name()+" has no valid tile at " +
                              str((self.x, self.y, self.z))+" in overworld", True)
            (self.x, self.y, self.z) = (0, 0, 1)
            self.dungeon = None
            tile = self.world.get_tile(self.x, self.y, self.z)
        tribe = tile.get_tribe()
        if tribe and (self in tribe.kobolds or self in tribe.tavern):
            t = tribe
        else:
            t = tile
        return t

    def show_wares(self, multi, sale=False):
        wares = []
        for i in self.items:
            val = int(i.realvalue*multi)
            if sale:
                val = int(val/2)
            if i.realvalue*multi > 0:
                wares.append(
                    i.display()+" - <:marblecoin:933132540926111814>"+str(val))
        if sale:
            return self.display()+"'s items (sell price):\n"+", ".join(wares)
        else:
            return self.display()+"'s items (buy price):\n"+", ".join(wares)

    def get_wares(self, worth=100):
        wares = {}
        for i in item_data:
            if i.get('value', 0) > 0 and not i.get("foreign", False):
                wares[i['name']] = i['value']
        while worth > 0 and len(self.items) < 10:
            w = choice(list(wares.keys()))
            item = spawn_item(w, self, force=True)
            if item.stack > 1:
                item.num = random.randint(1, item.stack)
            item.spawn_quality()
            if item.liquid_capacity > 0 and item.sealable:
                item.liquid_units = random.randint(0, item.liquid_capacity)
                if item.liquid_units > 0:
                    liqs = []
                    for l in liquid_data:
                        if not liquid_data[l].get("foreign", False):
                            liqs.append(l)
                    item.liquid = choice(liqs)
            worth -= item.realvalue

    def get_chan(self):
        if self.encounter:
            try:
                return self.encounter.get_party().get_chan()
            except:
                pass
        place = self.get_place()
        if isinstance(place, Tribe):
            return "tribe-"+str(place.id)+"-log"
        elif self.party:
            return self.party.chan
        elif self.commandedby and self.commandedby.get_place() == place:
            return self.commandedby.get_chan()
        else:
            return "exception-log"

    def get_name(self):
        if self.nick:
            return self.nick
        else:
            return self.name

    def has_item(self, name, q=1):
        return has_item(self, name, q)

    def consume_item(self, name, q=1):
        return consume_item(self, name, q)

    def auto_eat(k):
        area = list(k.items)+list(k.get_place().items)
        food = None
        fprio = -999
        for i in area:
            if i.perishable:
                prio = 100+(i.ap*10)
            else:
                prio = 100-(i.ap*10)
            if i.hp < 0:
                prio -= 200
            elif k.hp < k.max_hp:
                prio += i.hp*5
            if k.mp < k.max_mp:
                prio += i.mp*5
            if prio < 0 and not k.has_trait("starving"):
                continue
            if i.type == "food" and prio > fprio:
                food = i
                fprio = prio
        if food:
            food.use(k)
            return True
        return False

    def drink(self, liquid):
        if liquid in liquid_data:
            l = liquid_data[liquid]
        else:
            self.p("Liquid data for "+liquid+" not found, please report this!")
            return False
        if not l.get("drinkable", True):
            self.p(liquid+" is not drinkable.")
            return False
        if l.get("booze", False):
            good = self.get_drunk(liquid, l["ap"])
            if not good:
                return False
        elif not l.get("potion", False):
            if self.has_trait("hydrated"):
                self.p("[n] is already well-hydrated.")
                return False
            else:
                self.add_trait("hydrated")
                if l.get("ap", 0) > 0:
                    self.p("[n] guzzles down their "+liquid +
                           " and gains "+str(l["ap"])+" AP. Refreshing!")
                    self.ap_gain(l["ap"], False)
                else:
                    self.p("[n] guzzles down their "+liquid+". Refreshing!")
        if l.get("hp", 0) > 0:
            self.hp_gain(l["hp"])
        elif l.get("hp", 0) < 0:
            self.hp_tax(l["hp"]*-1, "Dangerous drink", dmgtype="poison")
        if l.get("mana", 0) > 0:
            self.mp_gain(l["mana"])
        if len(l.get("del_trait", [])) > 0:
            for t in l["del_trait"]:
                if self.has_trait(t):
                    self.del_trait(t)
                    self.p("[n] is no longer "+t+".")
        if len(l.get("add_trait", [])) > 0:
            for t in l["add_trait"]:
                if not self.has_trait(t):
                    self.add_trait(t)
                    self.p("[n] is now "+t+".")
        return True

    def watch_strength(k):
        defense = 0
        if k.equip:
            defense += (k.equip.dmg[0]*k.equip.dmg[1])+k.equip.dmg[2]
            if k.equip.type == "finesse":
                defense += max(k.smod("str", False),
                               k.smod("dex", False))+k.skmod("melee")
            elif k.equip.type == "melee":
                defense += k.smod("str", False)+k.skmod("melee")
            elif k.equip.type == "magic":
                defense += k.smod("int", False)+k.skmod("sorcery")
            else:
                defense += k.smod("dex", False)+k.skmod("marksman")
        else:
            defense += max(1, k.smod("str", False)+k.skmod("melee"))
        return defense

    def watch_damage(k, dmg, dmgto):
        defense = k.watch_strength()
        if k.equip and k.equip.type == "ranged":
            k.gain_xp("marksman", (dmg+10)*1.5)
        else:
            k.gain_xp("melee", (dmg+10)*1.5)
        if str(k.id) in dmgto:
            if k.equip:
                k.equip.lower_durability(dmgto[str(k.id)])
            k.hp_tax(dmgto[str(k.id)], "Killed in action", dmgtype=choice(
                ["bludgeoning", "slashing", "piercing"]))
            if k.save("wis") < 12:
                k.add_trait("stressed")
        return defense

    def spell_strength(self, spell):
        s = int(spell["strength"] *
                (1+((self.smod("int")+self.skmod("sorcery"))/5)))
        if self.wearing_nonmage_equipment():
            s = math.ceil(s/2)
        return s

    def age_up(k):
        console_print("aging up "+k.name)
        oldmax = k.max_hp
        stch = list(STATS)
        for st in STATS:
            k.s[st] += 1
        if k.color == "silver":
            points = 6
        elif k.color in ["brown", "orange", "purple"]:
            points = 4
        else:
            points = 3
            k.s[COLOR_STAT[k.color]] += 1
        if k.color == "orange":
            stch.extend(["str", "dex", "con"])
        elif k.color == "purple":
            stch.extend(["int", "wis", "cha"])
        while points > 0:
            if len(stch) == 0:
                break  # shouldn't happen, but just in case
            st = choice(stch)
            if k.s[st] < 14:
                k.s[st] += 1
                points -= 1
            stch.remove(st)
        k.hp += k.max_hp-oldmax

    def random_stats(self, color=None):
        points = 24
        for st in STATS:
            self.s[st] = 6
        while points > 0:
            st = choice(STATS)
            if self.s[st] < 14:
                self.s[st] += 1
                points -= 1
        self.hp = self.max_hp
        if not color:
            self.color = self.get_color_for_stats()
        else:
            self.color = color
            best = []
            bestam = 0
            rst = list(STATS)
            for st in rst:
                if self.s[st] == bestam:
                    best.append(st)
                elif self.s[st] > bestam:
                    bestam = self.s[st]
                    best = [st]
            if COLOR_STAT[color] not in best:
                self.s[choice(best)] = self.s[COLOR_STAT[color]]
                self.s[COLOR_STAT[color]] = bestam
            if len(best) > 1:
                for b in best:
                    if b != COLOR_STAT[color]:
                        self.s[b] -= 1
                        self.s[COLOR_STAT[color]] += 1
        self.random_genomes()

    def get_color_for_stats(self):
        orange = self.s["str"]+self.s["dex"]+self.s["con"]
        purple = self.s["int"]+self.s["wis"]+self.s["cha"]
        if orange > purple+10:
            return "orange"
        elif purple > orange+10:
            return "purple"
        m = sorted(self.s.items(), key=lambda kv: kv[1])
        if m[4][1] == m[5][1]:
            return "brown"
        else:
            return STAT_COLOR[m[5][0]]

    def random_skills(self):
        pass

    def random_genomes(self):
        while True:
            recount = []
            makepure = [self.color]
            if self.color == "orange":
                makepure = ["red", "black", "white"]
                if chance(50):
                    makepure.remove(choice(makepure))
                else:
                    makepure.append(choice(["yellow", "green", "blue"]))
            elif self.color == "purple":
                makepure = ["yellow", "green", "blue"]
                if chance(50):
                    makepure.remove(choice(makepure))
                else:
                    makepure.append(choice(["red", "black", "white"]))
            for g in GENOME:
                self.genome[g][0] = False
                self.genome[g][1] = False
                if g not in makepure:
                    if self.color != "brown" or chance(50):
                        self.genome[g][random.randint(0, 1)] = True
                    if chance(50):
                        self.genome[g][random.randint(0, 1)] = True
                    if not (self.genome[g][0] or self.genome[g][1]):
                        recount.append(g)
            if len(recount) == 1:  # generated brown cannot have exactly one pure color
                self.genome[recount[0]][random.randint(0, 1)] = True
            if len(recount) < 5:
                break
        pr = ""
        for g in self.genome:
            pr += g+":["+str(self.genome[g][0])+"," + \
                str(self.genome[g][1])+"]; "
        console_print(self.color+"="+pr)

    def attack(self, target):
        bestdmg = 0
        besti = None
        doattack = True
        for i in self.items+self.get_place().items:  # first determine which weapon is the best, and equip it
            d = (i.dmg[0]*i.dmg[1])+i.dmg[2]
            if i.type == "finesse":
                d += max(self.smod("str"), self.smod("dex"))
            elif i.type == "melee":
                d += self.smod("str")
            elif i.type == "magic":
                if self.mp <= 0:
                    d = 0
                else:
                    d += self.smod("int")
            elif i.type == "ranged":
                d += self.smod("dex")
                ammo = False
                for h in self.items:
                    if h.type == "ammo" and i.ammunition in h.name.lower():
                        d += (h.dmg[0]*h.dmg[1])+h.dmg[2]
                        ammo = True
                        break
                if not ammo:
                    d = 0
            if d > bestdmg:
                bestdmg = d
                besti = i
        # found a weapon that's better than the one we have now (or the one we're using is useless and we need to unequip)
        if besti != self.equip:
            if besti and besti not in self.items:  # weapon on the floor is better, grab it
                if len(self.items) >= self.inv_size:  # inventory full, drop something first
                    # just drop the first thing we have
                    cmd_drop([], self, self.items[0])
                cmd_get([], self, besti)
                doattack = False
            else:
                self.equip = besti
                if not self.equip:
                    self.p("[n] unequips their weapon.")
                else:
                    self.p("[n] equips their "+besti.display()+".")
        if doattack:
            cmd_attack(["!attack"], self, target)  # do the attack

    def display(self):
        d = self.get_name()
        p = self.get_place()
        if self.tribe:
            if self.tribe.chieftain == self:
                d = ":feather: "+d
            elif self.tribe.overseer == self:
                d = ":eyeglasses: "+d
        if self.has_trait("inactive"):
            d = ":zzz: "+d
        if self.has_trait("locked"):
            d = ":lock: "+d
        if isinstance(p, Tribe):
            if self in p.tavern:
                d = ":beer: "+d
        if self.has_trait("bound"):
            d = ":link: "+d
        if self.color == "black":
            if self.has_trait("nonbinary"):
                d = "<:actual_black_heart:971518820445487104> "+d
            elif self.male:
                d = "<:actual_black_square:927082316675813416> "+d
            else:
                d = "<:actual_black_circle:927082316369641524> "+d
        elif self.color == "red" and self.has_trait("nonbinary"):
            d = ":heart: "+d
        else:
            if self.color == "silver":
                shape = "button"
                if self.male:
                    c = "record"
                else:
                    c = "radio"
            else:
                c = self.color
                if self.has_trait("nonbinary"):
                    shape = "heart"
                elif self.male:
                    if c == "white":
                        shape = "large_square"
                    else:
                        shape = "square"
                else:
                    shape = "circle"
            d = ":"+c+"_"+shape+": "+d
        if self.nick:
            d = "**"+d+"**"
        if self.age < 6:
            d = "*"+d+"*"
        return d

    def char_info(self, k, pr=True):
        title = "Kobold info: "+self.display()
        msg = "Birth name: "+self.name+"\n"
        if self.nick:
            msg += "Tribal name: "+self.nick+"\n"
        else:
            msg += "Nameless"
            if self.has_trait("locked"):
                msg += " (Locked)"
            msg += "\n"
        if self.tribe:
            msg += "Tribe: "+self.tribe.name+" (ID: "+str(self.tribe.id)+")\n"
        else:
            msg += "Tribeless\n"
        msg += "Age: "+str(self.age)+" months\n"
        if self.has_trait("nonbinary"):
            msg += "Sex: Non-Binary"
        elif self.male:
            msg += "Sex: Male"
        else:
            msg += "Sex: Female"
        msg += "\nColor: "+self.color
        msg += "\nParents: "+", ".join(self.parents)
        msg += "\n\nStatus: "
        sts = []
        if len(self.eggs) > 0:
            sts.append("Pregnant")
        for t in trait_data:
            if self.has_trait(t) and trait_data[t].get("visible", False):
                sts.append(trait_data[t].get("display", t))
        if len(sts) > 0:
            msg += ", ".join(sts)
        else:
            msg += "Fine"
        msg += "\n\nHP: "+str(self.hp)+"/"+str(self.max_hp)
        msg += "\nAP: "+str(self.ap)+"/"+str(self.max_ap)
        if self.nick:
            msg += "\nCP: "+str(self.cp)+"/"+str(self.max_cp)
        if len(self.spells) > 0:
            msg += "\nMana: "+str(self.mp)+"/"+str(self.max_mp)
            msg += "\nSpells known: "+", ".join(self.spells)
        inv = []
        for i in self.items:
            inv.append(i.display())
        isize = len(inv)
        if self.carry:
            inv.append(self.carry.display())
        msg += "\n\nInventory ("+str(isize)+"/"+str(self.inv_size)+")\n"
        if len(inv) == 0:
            inv.append("Empty")
        msg += ", ".join(inv)+"\nWorn: "
        worn = []
        for w in self.worns:
            if self.worns[w]:
                worn.append(self.worns[w].display())
        if len(worn) == 0:
            worn.append("None")
        msg += ", ".join(worn)+"\n\nStats:\n"
        statblock = []
        for st in STATS:
            statblock.append(st+": "+self.stat_str(st))
        msg += " / ".join(statblock)
        msg += "\n\nSkills (total level: "
        sktotal = 0
        statblock = []
        for sk in skill_data:
            if self.skmod(sk) != 0:
                statblock.append(
                    skill_data[sk]["icon"]+skill_data[sk]["name"]+": "+str(self.skill_str(sk)))
            sktotal += self.skill[sk]
        msg += str(sktotal)+")\n"
        if len(statblock) > 0:
            msg += "\n".join(statblock)
        else:
            msg += "No skills yet..."
        if pr:
            action_queue.append(["embed", k.get_chan(), discord.Embed(
                type="rich", title=title, description=msg)])
        return msg

    def p(self, msg, party=False):
        msg = msg.replace("[n]", self.display())
        if party and self.party:
            game_print(msg, self.party.get_chan())
        else:
            chan = self.get_chan()
            if chan == "exception-log":
                self.broadcast(msg)
            else:
                game_print(msg, chan)

    def broadcast(self, msg):
        p = self.get_place()
        if isinstance(p, Tribe):
            game_print(msg, p.get_chan())
            return
        parties = []
        for k in self.world.kobold_list:
            if k.get_place() == p and k.party and k.party != self.party and k.party not in parties:
                parties.append(k.party)
        for a in parties:
            game_print(msg, a.get_chan())

    def accident(self, ch, n=2):
        if chance(ch):
            if self.worns["body"] and self.worns["body"].name == "Work Gear":
                n = math.ceil(n/2)
            self.hp_tax(n, "Accident")
            return True
        else:
            return False

    def mp_gain(self, n):
        self.mp += n
        if self.mp > self.max_mp:
            self.mp = self.max_mp
        self.p("[n] has gained "+str(n)+" mana.")

    def mp_tax(self, n):
        if n == 0:
            return True
        if self.mp >= n:
            self.mp -= n
            self.p("[n] spends "+str(n)+" mana (remaining: "+str(self.mp)+")")
            return True
        else:
            self.p("[n] doesn't have enough mana. (need " +
                   str(n)+", have "+str(self.mp)+")")
        return False

    def hp_gain(self, n):
        if self.hp == self.max_hp:
            return
        self.hp += n
        self.p("[n] gained "+str(n)+" HP.")
        if self.hp >= self.max_hp:
            self.hp = self.max_hp

    def hp_tax(self, n, cause, killer=None, dmgtype="bludgeoning"):
        if dmgtype == "fire" and self.has_trait("greased"):
            n *= 2
        self.hp -= n
        self.p("[n] lost "+str(n)+" HP.")
        if self.hp <= 0:
            self.die(cause, killer)
        else:
            if dmgtype not in ["poison", "arcane"] and n >= min(10, math.ceil(self.max_hp/2)) and self.save("con") < n+5:
                inj = []
                for t in trait_data:
                    if trait_data[t].get("injury", False) and (not self.has_trait(t) or not self.has_trait(trait_data[t].get("worse", t))):
                        inj.append(t)
                injury = choice(inj)
                if injury:
                    if self.has_trait(injury):
                        self.del_trait(injury)
                        injury = trait_data[injury]["worse"]
                    self.add_trait(injury)
            if dmgtype in ["slashing", "piercing"] and self.save("con") < 8:
                if not self.has_trait("infected"):
                    self.add_trait("infected_initial")
            trs = list(self.traits)
            for t in trs:
                if trait_data[t].get("hurt_reset", False):
                    self.del_trait(t)
                elif trait_data[t].get("hurt_save_to_cure", False):
                    if self.save(trait_data[t]["save_stat"]) >= trait_data[t]["save"]:
                        self.del_trait(t)
                        self.p("[n] has overcome their " +
                               trait_data[t].get("display", t)+" condition.")
            p = self.get_place()
            if isinstance(p, Tribe) and self in p.tavern and cause != "Dangerous drink" and not self.nick and not self.party:
                self.p("[n]: I don't have to stand for this!\n[n] leaves.")
                p.tavern.remove(self)
                if self in self.world.kobold_list:
                    self.world.kobold_list.remove(self)
            self.gain_xp("resilience", n*5)

    def get_soul_points(self, cause="General incompetence"):
        msg = "Soul point breakdown:\n\n"
        months = int(self.monthsnamed*((self.monthsnamed+1)/2))
        msg += "Months survived: " + \
            str(self.monthsnamed)+" (+"+str(months)+" SP)\n"
        sp = months
        skills = 0
        for s in self.skill:
            skills += self.skill[s]
        msg += "Total skills: "+str(skills)+" (+"+str(skills)+" SP)\n"
        sp += skills
        children = 0
        for k in self.world.kobold_list:
            if k.id in self.children and k.age >= 6:
                children += 1
        msg += "Children raised: "+str(children)+" (+"+str(children*3)+" SP)\n"
        sp += children*3
        get_pdata(self.d_user_id, "sp", 10)
        get_pdata(self.d_user_id, "sp_earned", 0)
        playerdata[str(self.d_user_id)]["sp"] += sp
        playerdata[str(self.d_user_id)]["sp_earned"] += sp
        msg += "\n**Total SP gained: " + \
            str(sp)+".** You now have " + \
            str(playerdata[str(self.d_user_id)]["sp"])+" Soul Points."
        embed = discord.Embed(
            type="rich", title=":skull_crossbones: **You are dead!** Cause: "+cause, description=msg)
        return embed

    def despawn(self):
        if self in self.world.kobold_list:
            self.world.kobold_list.remove(self)
        if self.encounter:
            if self in self.encounter.creatures:
                self.encounter.creatures.remove(self)
            if len(self.encounter.creatures) == 0:
                self.encounter.end()
        for t in self.world.tribes:
            if self in t.kobolds:
                t.kobolds.remove(self)
            if self in t.tavern:
                t.tavern.remove(self)
            if self in t.prison:
                t.prison.remove(self)

    def die(self, cause="General incompetence", killer=None):
        if self.has_trait("dead"):
            return
        self.add_trait("dead")
        self.p("[n] has died ("+cause+").")
        console_print(self.get_name()+" has died ("+cause+").", hp=True)
        if self.carry:
            (self.carry.x, self.carry.y, self.carry.z) = (self.x, self.y, self.z)
            self.p(self.carry.display()+" falls to the ground.")
        for l in self.world.kobold_list:
            if l.carry == self:
                l.carry = None
                l.del_trait("carried")
        # murderer! (not suicide)
        if killer and killer != self and getattr(killer, "tribe", None):
            killer.tribe.gain_heat(5)
            killer.p(
                self.display()+"'s blood is on [n]'s hands... The tribe's heat has increased.")
        t = self.get_place()
        if self.nick:
            if self.world != sandbox:
                action_queue.append(
                    ["delrole", ROLENAMES[self.color], self.d_user_id])
                action_queue.append(["delrole", "Chieftain", self.d_user_id])
                action_queue.append(["addrole", "Lost Soul", self.d_user_id])
            action_queue.append(
                ["embed", self.d_user_id, self.get_soul_points(cause)])
            msg = self.char_info(self, pr=False)
            e = discord.Embed(
                type="rich", title="Final moments: "+self.display(), description=msg)
            action_queue.append(["embed", self.d_user_id, e])
        corpse = spawn_item("Kobold Corpse", t)
        corpse.owner = self.get_name()
        inv = list(self.items)
        for i in inv:
            i.move(t, tumble=True)
        if self.tribe:
            if self in self.tribe.kobolds:
                self.tribe.kobolds.remove(self)
            if self in self.tribe.watchmen:
                self.tribe.watchmen.remove(self)
        if self in self.world.kobold_list:
            self.world.kobold_list.remove(self)
        if self.party:
            self.party.leave(self, reform=False)
        if not isinstance(t, Tribe) and t.camp:
            if self in t.camp["watch"]:
                t.camp["watch"].remove(self)
        if self.encounter:
            if self in self.encounter.creatures:
                self.encounter.creatures.remove(self)
            if len(self.encounter.creatures) == 0:
                self.encounter.end()

    def add_trait(self, t):
        trs = list(self.traits)
        for u in trs:
            if t in trait_data[u].get("immune", []):
                return
        if t not in self.traits:
            self.traits.append(t)
        else:
            return
        if trait_data[t].get("contract_msg", None):
            self.p(trait_data[t]["contract_msg"])
        if t == "onearm" or t == "noarms":
            if self.equip:
                self.equip = None
        for u in trs:
            if trait_data[u].get("removed_by", None) == t:
                self.del_trait(u)
            if trait_data[u].get("combine_with", None) == t:
                self.del_trait(u)
                self.del_trait(t)
                self.add_trait(trait_data[u]["combine_into"])

    def del_trait(self, t):
        if t in self.traits:
            self.traits.remove(t)
        if trait_data[t].get("add_on_remove", None):
            self.add_trait(trait_data[t]["add_on_remove"])

    def has_trait(self, t):
        if t in self.traits:
            return True
        else:
            return False

    def gain_fam(self, req, exp):
        for r in req:
            if r[0] == "research":
                self.get_familiar(r[1], exp)

    def learn_spell(self, lv, c):
        sp = []
        for s in spell_data:
            if s["name"] not in self.spells and s["level"] <= lv and (not c or c in s["spell_class"]):
                sp.append(s["name"])
        newspell = choice(sp)
        if newspell:
            self.spells.append(newspell)
            self.p("[n] has learned the "+newspell+" spell!")

    def gain_xp(self, sk, exp):
        if (self.has_trait("inactive") or not self.nick) and self.skill[sk] >= 5:
            return
        if self.color == STAT_COLOR[skill_data[sk]["stat"]] or self.color == "silver":
            exp *= 1.5
        if self.color == "brown":
            exp = exp*1.2
        if self.color == "orange" and skill_data[sk]["stat"] in ["str", "dex", "con"]:
            exp = exp*1.35
        if self.color == "purple" and skill_data[sk]["stat"] in ["int", "wis", "cha"]:
            exp = exp*1.35
        if self.nick:
            exp = exp*1.1
        exp = int(exp)
        if exp <= 0:
            return
        self.skillxp[sk] += exp
        console_print(self.get_name()+" gained "+str(exp)+" "+sk+" exp")
        tonext = 100+((self.skill[sk]*(self.skill[sk]+1)/2)*50)
        oldmax = self.max_hp
        while self.skillxp[sk] > tonext:
            self.skillxp[sk] -= tonext
            self.skill[sk] += 1
            tonext = 100+((self.skill[sk]*(self.skill[sk]+1)/2)*50)
            self.p("[n] has advanced to level "+str(self.skill[sk]) +
                   " "+skill_data[sk]["icon"]+skill_data[sk]["name"]+"!")
            statblock = 0
            for s in skill_data:
                if skill_data[s]["stat"] == skill_data[sk]["stat"]:
                    statblock += self.skill[s]
            if statblock % 4 == 0 and self.s[skill_data[sk]["stat"]] < 20:
                self.s[skill_data[sk]["stat"]] += 1
                self.p("[n] has achieved a "+skill_data[sk]["stat"].upper() +
                       " score of "+str(self.s[skill_data[sk]["stat"]])+"!")
            if sk == "sorcery":
                self.learn_spell(self.skill["sorcery"]/2, "arcane")
            elif sk == "druid":
                self.learn_spell(self.skill["druid"]/2, "druid")
            elif sk == "faith":
                self.learn_spell(self.skill["faith"]/2, "draconic")
        if self.max_hp > oldmax:
            self.hp += self.max_hp-oldmax

    def equip_best(self, type):
        best = None
        bestam = 0
        if not self.shaded:
            umb = True
        else:
            umb = False
        for i in self.items:
            if i.tool == type:
                if i.toolpower > bestam:
                    best = i
                    bestam = i.toolpower
                elif i.name == "Silk Parasol" and umb and not best:
                    best = i
        if best and self.equip != best:
            cmd_equip([], self, best)

    def equip_bonus(self, type):
        p = 0
        if self.tribe:
            o = self.tribe.overseer
            if o and o != self and o.get_place() == self.get_place():
                p += max(1, o.smod("cha")+o.skmod("command"))
        elif self.has_trait("broken"):
            p -= 10
            place = self.get_place()
            best = None
            bestp = -10
            for k in self.world.kobold_list:
                if k.get_place() == place:
                    ip = k.skmod("intimidation")+k.smod("cha")
                    if not best or bestp < ip:
                        best = k
                        bestp = ip
            p += bestp
            best.gain_xp("intimidation", 5)
        if self.equip and self.equip.tool == type:
            p += max(1, math.floor(self.equip.toolpower *
                     2*(1+(self.equip.quality/5))))+5
            self.equip.lower_durability()
        return p

    def get_drunk(self, liquid, ap):
        if self.has_trait("hungover"):
            self.p(
                "Just the thought of this makes [n] sick to their stomach. Better give them some time.")
            return False
        self.p("[n] chugs their "+liquid+"...")
        if self.has_trait("stressed") and self.save("wis")+self.booze_ap+ap >= 12:
            self.del_trait("stressed")
            self.p("[n] is feeling a lot more relaxed after that.")
        if self.has_trait("drunk"):
            if self.save("con") < 2+ap+max(0, 6-self.age)+self.booze_ap:
                self.p(
                    "[n] passes out... they wake up some time later with a deathly headache.")
                self.add_trait("hungover")
                self.ap = 0
                return True
        else:
            self.add_trait("drunk")
        self.ap_gain(ap, False)
        self.booze_ap += ap
        self.p("[n] is pleasantly buzzed and gains "+str(ap)+" AP.")
        return True

    def best_trader(self):
        best = self.smod("cha", False)+self.skmod("negotiation")
        multi = 1-min(0.25, best/50)
        return (multi, best, self)

    def breed(self, partner, force=False, pullout=False):
        self.add_trait("breed")
        partner.add_trait("breed")
        exp = 35
        ch = 50
        fert = self.skmod("vitality")+partner.skmod("vitality")
        ch += fert*5
        if ch > 90:
            ch = 90
        if force or chance(ch):
            exp *= 2
            console_print("Breeding attempt between "+self.get_name() +
                          " and "+partner.get_name()+" successful.")
            self.p("The session between [n] and "+partner.display() +
                   " went very well! Both are satisfied.")
            if pullout:
                self.p(
                    "They were not trying for offspring this time, but each one's vitality has increased significantly.")
            elif (self.has_trait("nonbinary") or partner.has_trait("nonbinary") or self.male != partner.male) and not (self.has_trait("infertile") or partner.has_trait("infertile")):
                if self.male or (not partner.male and self.has_trait("nonbinary")):
                    female = partner
                    male = self
                    female.father = self
                else:
                    female = self
                    male = partner
                    female.father = partner
                e = random.randint(1, 4)
                for i in range(e):
                    baby = make_baby(male, female)
                    female.eggs.append(baby)
                    male.children.append(baby.id)
                    female.children.append(baby.id)
                female.p(
                    "[n] should expect a clutch of eggs at the end of the month, as long as the mother is well-fed.")
            else:
                self.p(
                    "They were not capable of having children together, but each one's vitality has increased significantly.")
        else:
            self.p("The session between [n] and "+partner.display(
            )+" didn't exactly go as planned... but each one's vitality has increased a little.")
        self.gain_xp("vitality", exp)
        partner.gain_xp("vitality", exp)
