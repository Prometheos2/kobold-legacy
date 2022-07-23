import math
import random
import time

import discord

from creature import Creature
from kobold import Kobold
from tribe import Tribe

from ..kobold import action_queue
from ..kobold import chance
from ..kobold import game_print
from ..kobold import guild
from ..kobold import landmark_data
from ..kobold import liquid_data
from ..kobold import sandbox
from ..kobold import trait_data


class Party:
    def __init__(self, owner):
        self.owner = owner
        if owner.world == sandbox:
            if owner.world.pid < 8989:
                owner.world.pid = 8989
        self.id = owner.world.pid
        owner.world.pid += 1
        self.members = [owner]
        self.invites = []
        self.chan = "party-"+str(self.id)
        chan = discord.utils.get(guild.channels, name=self.chan)
        if not chan:
            action_queue.append(["newchan", self.chan])
        action_queue.append(["addmember", self.chan, owner.d_user_id])
        game_print(owner.display()+" has formed the party.", self.chan)
        self.owner.party = self

    def __iter__(self):
        self.member_index = 0
        return self

    def __next__(self):
        if self.member_index < len(self.members):
            result = self.members[self.member_index]
            self.member_index += 1
            return result
        else:
            raise StopIteration

    @property
    def k_members(self):
        m = []
        for k in self.members:
            if isinstance(k, Kobold):
                m.append(k)
        return m

    @property
    def c_members(self):
        m = []
        for k in self.members:
            if not isinstance(k, Kobold):
                m.append(k)
        return m

    def get_chan(self):
        return self.chan

    def broadcast(self, msg):
        p = self.owner.get_place()
        if isinstance(p, Tribe):
            return
        parties = []
        for k in self.owner.world.kobold_list:
            if k.get_place() == p and k.party and k.party != self and k.party not in parties:
                parties.append(k.party)
        for a in parties:
            game_print(msg, a.get_chan())

    def join(self, k):
        if k not in self.members:
            self.members.append(k)
            k.party = self
            if k.nick:
                action_queue.append(["addmember", self.chan, k.d_user_id])
            game_print(k.display()+" has joined the party.", self.chan)

    def leave(self, k, reform=True):
        if k in self.members:
            self.members.remove(k)
            if k.hp > 0 and k.nick:
                # if dead, your ghost can still watch things
                action_queue.append(["delmember", self.chan, k.d_user_id])
            game_print(k.display()+" has left the party.", self.chan)
            k.party = None
            if isinstance(k, Creature):
                place = self.owner.get_place()
                if isinstance(place, Tribe) and place.has_building("Kennel") and k not in place.kennel:
                    place.kennel.append(k)
                    k.p("[n] is stationed in the kennel.")
                elif not isinstance(place, Tribe) and "Pasture" in place.special and k not in place.pasture:
                    place.pasture.append(k)
                    k.p("[n] is stationed in the pasture.")
            elif self.owner == k:
                eligible = None
                lastactive = 0
                for m in self.k_members:
                    if m.nick and m.lasttime > lastactive:
                        eligible = m
                        lastactive = m.lasttime
                if eligible:
                    self.owner = eligible
                    game_print(self.owner.display() +
                               " has been made party leader.", self.chan)
                else:
                    mem = list(self.members)
                    for m in mem:
                        self.leave(m)
            if k.nick and k.hp > 0:  # dead bolds immediately reform a party otherwise
                place = k.get_place()
                if not isinstance(place, Tribe) and reform:  # in the overworld
                    k.party = Party(k)
        if not isinstance(k, Creature) and len(self.members) <= 0:
            action_queue.append(["delchan", self.chan, time.time()+600])

    def stealth_roll(self, encounter, bonus=0, me=None, aps=0):
        if not encounter.hostile:
            return
        if self.owner.tribe and encounter.creatures[0].faction in self.owner.tribe.shc_faction and self.owner.tribe.shc_faction[encounter.creatures[0].faction] < 1:
            encounter.hostile = False
            self.owner.p(
                "The "+encounter.creatures[0].faction+" faction has called a truce with the kobolds, so they are not hostile.")
            return
        stealth = bonus
        if me and isinstance(me, Kobold):
            stealth += random.randint(1, 20)+me.stealth
            me.stealthrolls += 1
        else:
            for k in self.k_members:
                stealth += random.randint(1, 20)+k.stealth
                k.stealthrolls += 1
            stealth = int(stealth/len(self.k_members))-len(self.members)+1
        percep = 0
        for c in encounter.creatures:
            percep += random.randint(1, 20)+c.smod("wis")
        percep = int(percep/len(encounter.creatures)) + \
            len(encounter.creatures)-1
        if stealth >= percep:
            self.owner.p("The party manages to remain undetected.")
            exp = percep-bonus
            encounter.examine(self.owner)
        else:
            self.owner.p("The party is spotted! Combat is initiated!")
            exp = stealth
            encounter.start(self)
        exp += 10
        if isinstance(me, Creature):
            return
        if me:
            exp -= me.stealthrolls*3
            me.gain_xp("stealth", exp*(aps+1))
        else:
            for k in self.k_members:
                k.gain_xp("stealth", (exp*(aps+1))-(k.stealthrolls*3))

    def best_trader(self):
        best = -5
        nego = None
        for m in self.k_members:
            n = m.smod("cha", False)+m.skmod("negotiation")
            if n > best:
                best = n
                nego = m
        multi = 1-min(0.25, best/50)
        return (multi, best, nego)

    def move(self, x, y, z, cost):
        self.broadcast(self.owner.display()+"'s party has left the area.")
        mem = list(self.k_members)
        oldplace = self.owner.get_place()
        for k in mem:
            p = k.get_place()
            hmc = 0
            if not k.has_trait("carried"):
                hmc = 100*cost
                for t in k.traits:
                    hmc += trait_data[t].get("move_ap", 0)*100
            else:
                for m in self.c_members:
                    if m.carry == k:
                        hmc = (100*cost)-(m.mount_strength())
                        if hmc < 50*cost:
                            hmc = 50
                        break
            for l in p.special:
                if l in landmark_data:
                    hmc *= landmark_data[l].get("move_cost", 1)
            hmc = math.floor(hmc)
            if p.camp and k in p.camp["watch"]:
                p.camp["watch"].remove(k)
            (k.x, k.y, k.z) = (x, y, z)
            k.hiding = 100
            k.stealthrolls = 0
            if k.carry:
                (k.carry.x, k.carry.y, k.carry.z) = (x, y, z)
                if k.carry.age >= 3:
                    if k.save("str") < 10+min(k.carry.age, 6):
                        k.p("[n] is burdened with carrying " +
                            k.carry.display()+".")
                        dmg = cost
                        if k.ap >= cost:
                            hmc += 100*cost
                        else:
                            dmg += max(cost, math.floor(k.movement+hmc/100))
                        k.hp_tax(dmg, "Overburdened")
            for i in k.items:
                if i.name == "Crude Map":
                    i.map_update(k)
                if i.liquid and not i.sealable and i.liquid_units > 0 and not liquid_data[i.liquid].get("powder", False) and k.equip != i and k.save("dex") < 15:
                    if chance((i.liquid_units/i.liquid_capacity)*100):
                        k.p("[n] spills some of their "+i.liquid+".")
                        i.liquid_units -= 1
            #console_print("movement cost "+str(hmc))
            k.movement += hmc
            if k.movement >= 100:
                k.ap_tax(min(k.ap, math.floor(k.movement/100)))
                k.movement = k.movement % 100
        mcm = list(self.c_members)
        if not hasattr(p, "pasture"):
            p.pasture = []
        for c in mcm:
            if c in p.pasture:
                p.pasture.remove(c)
            if oldplace.camp and c in oldplace.camp["watch"]:
                oldplace.camp["watch"].remove(c)
            if c.carry:
                c.carry.x, c.carry.y, c.carry.z = self.owner.x, self.owner.y, self.owner.z
                if c.carry not in self.k_members:
                    hmc = (100*cost)-(c.mount_strength())
                    if hmc < 50*cost:
                        hmc = 50
                    for l in p.special:
                        if l in landmark_data:
                            hmc *= landmark_data[l].get("move_cost", 1)
                    c.carry.movement += hmc
                    if c.carry.movement >= 100:
                        c.carry.ap_tax(math.floor(c.carry.movement/100))
                        c.carry.movement = c.carry.movement % 100
        if self.owner.dungeon:
            t = self.owner.dungeon.get_tile(x, y, z)
        else:
            t = self.owner.world.get_tile(x, y, z)
        t.examine(self.owner)
        for e in self.owner.world.encounters:
            if e.place == t:
                if len(e.creatures) == 0:
                    continue  # shrug
                if isinstance(e.creatures[0], Kobold):
                    if e.creatures[0].age < 6:
                        self.owner.p(
                            "There is a lost kobold child here, all alone.")
                    elif len(e.creatures) > 1:
                        if isinstance(e.creatures[1], Kobold):
                            self.owner.p(
                                "There is a group of hunters from a rogue kobold tribe here.")
                        else:
                            self.owner.p(
                                "There is a wandering merchant and their two pack bears here. They seem to have some items for sale.")
                    else:
                        self.owner.p(
                            "There is a wandering kobold here. They seem lost and afraid.")
                else:
                    if len(e.creatures) > 1:
                        self.owner.p("There is a group of " +
                                     str(e.creatures[0].basename)+" here!")
                    else:
                        self.owner.p(
                            "There is a "+e.creatures[0].basename+" here!")
                    passive = True
                    for c in e.creatures:
                        if not c.passive:
                            passive = False
                    if not passive:
                        self.stealth_roll(e, aps=cost)
                    else:
                        e.hostile = False
        self.broadcast(self.owner.display()+"'s party has entered the area.")
