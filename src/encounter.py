import random

import discord

from creature import Creature
from kobold import Kobold

from ..kobold import (action_queue, chance, choice,
                      console_print, creature_data, game_print,
                      spawn_item, trait_data)


class Encounter:
  def __init__(self,world,tile,n,level,force=None):
    self.place=tile
    self.world=world
    self.creatures=[]
    world.encounters.append(self)
    creatures=[]
    self.engaged=[]
    self.special=None
    self.hostile=True
    self.pacified=False
    if (not force and chance(25)) or force=="kobold":
      self.hostile=False
      type=choice(["merchant","wanderer","child","hunters"])
      if force=="kobold": type="merchant"
      if type=="hunters": a=random.randint(2,5)
      else: a=1
      for b in range(a):
        k=Kobold(world.tribes[0])
        k.tribe=None
        k.encounter=self
        (k.x,k.y,k.z) = (tile.x,tile.y,tile.z)
        if type=="child":
          k.age=random.randint(1,5)
          k.random_stats()
          for st in k.s: k.s[st]=0
          for x in range(k.age): k.age_up()
          k.hp=k.max_hp
        else: 
          k.random_stats()
          if type=="hunters":
            w=choice(["Stone Spear","Stone Hammer","Stone Knife","Sling","Stone Spear","Stone Hammer","Stone Knife","Sling","Copper Spear","Copper Hammer","Copper Knife","Bone Bow"])
            item=spawn_item(w,k)
            item.spawn_quality()
            if w=="Sling": spawn_item("Stone Pebble",k,random.randint(20,40))
            if w=="Bone Bow": spawn_item("Bone Arrow",k,random.randint(10,20))
        k.ap=k.max_ap
        self.creatures.append(k)
      if type=="merchant":
        k.add_trait("trader")
        for c in creature_data:
          if c['name']=='Bear':
            c=Creature('Bear',world,self)
            c.name='Merchant Bear A'
            c=Creature('Bear',world,self)
            c.name='Merchant Bear B'
            break
        k.get_wares()
    elif n>0:
      self.hostile=True
      if force: mob=force
      else:
        for c in creature_data:
          if c["level"][0]<=level and c["level"][1]>=level and (c["cr"]*2<n or c["cr"]<=1):
            creatures.append(c["name"])
        console_print("spawning from "+str(n)+": "+str(creatures))
        mob=choice(creatures)
      if not mob: mob="Dopple"
      self.populate(mob,n)
      
  def populate(self,mob,n):
    spawned=n
    a=ord("A")
    while n>0 and len(self.creatures)<8:
      cr=Creature(mob,self.world,self)
      if spawned>1:
        try: cr.name+=" "+chr(a)
        except: cr.name+="error"
      a+=1
      n-=max(1,cr.cr)
    console_print("Spawned "+str(len(self.creatures))+" "+mob+" (n="+str(spawned)+")")
    
  def start(self,party):
    if party.owner.tribe and not isinstance(self.creatures[0],Kobold) and self.creatures[0].faction in party.owner.tribe.shc_faction and party.owner.tribe.shc_faction[self.creatures[0].faction]<1:
      party.owner.tribe.violate_truce(party.owner,self.creatures[0].faction)
    self.engaged.append(party)
    self.new_turn(party)
    self.examine(party.owner)
    
  def end(self):
    if self in self.world.encounters: self.world.encounters.remove(self)
    for p in self.engaged: game_print("The battle is won!",p.get_chan())
    self.disengage_all()
    if self.special=="Goblin Boss":
      if self.place.dungeon:
        d=self.place.dungeon
        ow=self.world.get_tile(d.x,d.y,d.z)
        if "Goblin Camp" in ow.special: ow.special.remove("Goblin Camp")
        game_print("With their boss defeated, the remaining goblins scramble to flee the camp. The goblins won't be planning a counter-attack any time soon, but you can bet they won't forget this.",p.get_chan())
        if p.owner.tribe:
          p.owner.tribe.heat_faction["Goblin"]=int(p.owner.tribe.heat_faction["Goblin"]/-2)
          p.owner.tribe.shc_faction["Goblin"]+=50
    elif self.special=="Ant Queen":
      if self.place.dungeon:
        d=self.place.dungeon
        ow=self.world.get_tile(d.x,d.y,d.z)
        if "Ant Nest" in ow.special: ow.special.remove("Ant Nest")
        if "Abandoned Ant Nest" not in ow.special: ow.special.append("Abandoned Ant Nest")
        game_print("The Ant Queen and her subjects fall, leaving behind the heavy stench of alarm pheromones. The nest rumbles as ants scramble to evacuate. These ants surely won't bother the tribe anytime soon.",p.get_chan())
        tiles=[]
        for m in d.map:
          tiles.append(d.map[m])
        re=[]
        for e in self.world.encounters:
          if e.place in tiles:
            e.disengage_all()
            re.append(e)
        for e in re: self.world.encounters.remove(e)
        ts=[]
        for m in p.k_members:
          if m.tribe and m.tribe not in ts: ts.append(m.tribe)
        for t in ts: t.heat_faction["Ant"]=0
        game_print("This has been an enlightening experience for everyone.",p.get_chan())
        for m in p.k_members: m.get_familiar("Verticality",600)
        
  def disengage(self,party):
    for k in party.members:
      ts=list(k.traits)
      for t in ts:
        if trait_data[t].get("end_combat",False): k.traits.remove(t)
    while party in self.engaged: self.engaged.remove(party)
    
  def disengage_all(self):
    ps=list(self.engaged)
    for p in ps: self.disengage(p)
    
  def pac_check(self):
    pac=True
    for c in self.creatures:
      if not c.has_trait("pacified") and not c.has_trait("sleep"): pac=False
    if pac:
      for p in self.engaged: 
        if p.owner and p.owner.nick: p.owner.p("All enemies are pacified. We are out of initiative.")
      self.disengage_all()
      self.hostile=False
      self.pacified=True
      
  def examine(self,me):
    title="Encounter"    
    msg="Creatures here:"
    for c in self.creatures:
      msg+="\n"+c.display()
    if me.party in self.engaged:
      msg+="\n\nParty members waiting to act:\n"
      pm=[]
      for k in me.party.members:
        if not k.didturn: 
          d=k.display()
          if k.has_trait("haste"): d+=" (x2)"
          pm.append(d)
      msg+=", ".join(pm)
    else: 
      if self.hostile: msg+="\n\nYou are not engaged. You can type !fight to attempt an ambush and start combat."
      else: msg+="\n\nThis encounter is not hostile. You can type !fight to attempt an ambush and attack them anyway."
    action_queue.append(["embed",me.get_chan(),discord.Embed(type="rich",title=title,description=msg)])
    return msg
    
  def enemy_turn(self,party):
    self.pac_check()
    if party not in self.engaged: return
    targets=[]
    for k in party.members:
      if k.aggro: targets.append(k)
      targets.append(k)
      trs=list(k.traits)
      for t in trs:
        if trait_data[t].get("turn_reset",False): k.del_trait(t)
    for c in self.creatures:
      c.didturn=False
      turn_traits(c)
      if not c.didturn:
        if c.has_trait("confused"):
          target=choice(self.creatures)
          c.p("[n] stumbles around in a daze...")
          args=["attack"]
        else:
          target=choice(targets)
          targ=target
          if hasattr(c,"actions"): act=choice(c.actions)
          else: act=None
          if act:
            args=act.split(":")
            if len(args)>1: 
              target=list(args)
              target[0]=targ
          else: args=["attack"]
        if target:
          getattr(c,args[0])(target)
          if isinstance(target,Kobold) and target.hp<=0: targets.remove(target) #target dead, don't beat a dead kobold
        if c.has_trait("shaker"):
          game_print(c.display()+" stomps the ground. The cavern rumbles ominously...",party.get_chan())
          self.place.stability-=5
          self.place.cave_in(party.owner)
      trs=list(c.traits)
      for t in trs:
        if trait_data[t].get("turn_reset",False): c.del_trait(t)
      if len(targets)==0: #total party wipe
        self.disengage(party)
        return
    self.new_turn(party)
      
  def new_turn(self,party):
    for k in party.members: 
      k.didturn=False
      k.aggro=False
      k.del_trait("dodging")
      k.guardian=None
      turn_traits(k)
      if k.has_trait("confused"):
        target=choice(k.party.members)
        k.p("[n] stumbles around in a daze...")
        k.attack(target)
        k.didturn=True
      if isinstance(k,Creature) and "combat" not in k.training and "guard" not in k.training: k.didturn=True
      
  def get_party(self):
    return self.place.get_party()[0]
    
  def get_chan(self):
    return self.get_party().get_chan()

def turn_traits(fighter):
  trs=list(fighter.traits)
  for t in trs:
    if trait_data[t].get("turn_block",False): 
      fighter.didturn=True
      if trait_data[t].get("visible",False): fighter.p("[n] is "+trait_data[t].get("display",t)+" and cannot act this round.")
    if trait_data[t].get("dmg_combat",0)>0: fighter.hp_tax(trait_data[t]["dmg_combat"],trait_data[t].get("display",t),dmgtype="poison")
    if trait_data[t].get("turn_save_to_cure",False):
      if fighter.save(trait_data[t]["save_stat"])>=trait_data[t]["save"]:
        fighter.del_trait(t)
        fighter.p("[n] has overcome their "+trait_data[t].get("display",t)+" condition.")
