import math
import random

import discord

from creature import Creature
from kobold import Kobold
from tile import Tile
from tribe import Tribe

from ..kobold import (STATS, action_queue, attack_roll, chance,
                      choice, console_print, creature_data,
                      droll, game_print, spawn_item, trait_data)


class Creature:
  def __init__(self,name,world,encounter):
    self.world=world
    self.encounter=encounter
    self.encounter.creatures.append(self)
    for i in creature_data:
      if i["name"]=="Default":
        for k in i.keys(): 
          if not isinstance(i[k],list): setattr(self,k,i[k])
          else: setattr(self,k,list(i[k]))
      if i["name"]==name:
        for k in i.keys(): 
          if not isinstance(i[k],list): setattr(self,k,i[k])
          else: setattr(self,k,list(i[k]))
        break
    self.max_hp=self.hp
    self.basename=name
    self.owner=None
    self.party=None
    self.training=[]
    self.training_prog={}
    self.items=[]
    self.searched=[]
    self.didturn=False
    self.carry=None
    self.dungeon=None
    self.guardian=None
    
  @property
  def nick(self):
    return None
    
  @property
  def inv_size(self):
    if self.hp<=0: return -10
    inv=self.smod("str",False)+5
    for i in self.items: inv+=i.inv_size
    if self.carry: inv-=1
    return inv
    
  @property
  def worns(self):
    return {}
    
  def wearing_nonmage_equipment(self):
    return False
    
  def stat_str(self,stat):
    st=self.stats[stat]
    for t in self.traits:
      if stat in trait_data[t].get("stats",{}): st+=trait_data[t]["stats"][stat]
    ret=str(st)
    if st!=self.stats[stat]: ret=str(self.stats[stat])+" ["+ret+"]"
    return ret
    
  def watch_strength(k):
    return (k.dmg[0]*k.dmg[1])+k.dmg[2]
    
  def watch_damage(k,dmg,dmgto):
    defense=k.watch_strength()
    if k.name in dmgto: k.hp_tax(dmgto[k.name],"Killed in action",dmgtype=choice(["bludgeoning","slashing","piercing"]))
    return defense
    
  def mount_strength(k):
    return max(0,(k.stats["str"]+k.stats["con"])-8)*3
    
  def char_info(self,k,pr=True):
    title="Creature info: "+self.display()
    msg="Name: "+self.name+"\n"
    msg+="Species: "+self.basename+"\n"
    msg+="Diet: "+", ".join(self.diet)+"\n"
    if len(self.products)>0: msg+="Products: "+", ".join(self.products)+"\n"
    if self.owner: 
      if self.owner.hp>0: msg+="Owner: "+self.owner.display()+"\n"
      else: msg+="Unowned\n"
    else: msg+="Wild\n"
    msg+="Training ("+str(len(self.training))+"/"+str(self.stats["int"])+"): "+", ".join(self.training)+"\n"
    if len(self.training)>=self.stats["int"]: msg+="No further training is possible.\n"
    else:
      msg+="Training progress:\n"
      maxprog=(len(self.training)+1)*100
      for t in self.training_prog:
        if t not in self.training: msg+=t+" - "+str(self.training_prog[t])+"/"+str(maxprog)+"\n"
    if "mount" in self.training: msg+="Mount strength: "+str(self.mount_strength())+"\n"
    msg+="\nStatus: "
    sts=[]
    for t in trait_data: 
      if self.has_trait(t) and trait_data[t].get("visible",False): sts.append(trait_data[t].get("display",t))
    if len(sts)>0: msg+=", ".join(sts)
    else: msg+="Fine"
    msg+="\n\nHP: "+str(self.hp)+"/"+str(self.max_hp)
    inv=[]
    for i in self.items:
      inv.append(i.display())
    isize=len(inv)
    if self.carry: inv.append(self.carry.display())
    msg+="\n\nInventory ("+str(isize)+"/"+str(self.inv_size)+")\n"
    if len(inv)==0: inv.append("Empty")
    msg+=", ".join(inv)+"\n\nStats:\n"
    statblock=[]
    for st in STATS:
      statblock.append(st+": "+self.stat_str(st))
    msg+=" / ".join(statblock)
    if pr: action_queue.append(["embed",k.get_chan(),discord.Embed(type="rich",title=title,description=msg)])
    return msg
    
  def get_place(self):
    if self.encounter: return self.encounter.place
    elif self.party: return self.party.owner.get_place()
    else:
      for t in self.world.tribes:
        if self in t.kennel: return t
      for m in self.world.map:
        if self in self.world.map[m].pasture: return self.world.map[m]
    return None
    
  def smod(self,stat,rand=True): #this is the CREATURE smod
    st=self.stats[stat]
    for t in self.traits:
      if stat in trait_data[t].get("stats",{}): st+=trait_data[t]["stats"][stat]
    if rand: st+=random.randint(0,1)
    return math.floor((st-10)/2)
    
  def save(self,stat):
    s=droll(1,20)+self.smod(stat)
    console_print(self.name+" rolls a "+stat+" save and gets "+str(s))
    return s
    
  def get_name(self):
    return self.name
  
  def display(self):
    if self.owner: n="*"+self.name+"*"
    else: n=self.name
    return self.emoji+n
    
  def get_chan(self):
    try: 
      if self.party: return self.party.owner.get_chan()
      else: return self.get_place().get_chan()
    except: return "exception-log"
    
  def p(self,msg):
    msg=msg.replace("[n]",self.display())
    game_print(msg,self.get_chan())
    
  def hp_gain(self,n):
    self.hp+=n
    self.p("[n] gained "+str(n)+" HP.")
    if self.hp>self.max_hp: self.hp=self.max_hp
  
  def hp_tax(self,n,cause,killer=None,dmgtype="bludgeoning"):
    if dmgtype in self.dmg_immune: return
    if dmgtype=="fire" and self.has_trait("greased"): n*=2
    if dmgtype in self.dmg_weak: n*=2
    if dmgtype in self.dmg_resist: n=math.floor(n/2)
    self.hp-=n
    self.p("[n] lost "+str(n)+" HP.")
    trs=list(self.traits)
    for t in trs:
      if trait_data[t].get("hurt_reset",False): self.del_trait(t)
      elif trait_data[t].get("hurt_save_to_cure",False):
        if self.save(trait_data[t]["save_stat"])>=trait_data[t]["save"]:
          self.del_trait(t)
          self.p("[n] has overcome their "+trait_data[t].get("display",t)+" condition.")
    if self.has_trait("relentless") and self.max_hp-n<=0 and n<math.ceil(self.max_hp/2) and self.hp>1:
      self.hp=1
      self.p("[n] hangs on by a thread!")
      return
    if self.hp<=0:
      self.die(killer)
      
  def has_trait(self,trait):
    return trait in self.traits
    
  def add_trait(self,trait):
    if trait in self.trait_immune: return
    if trait not in self.traits: self.traits.append(trait)
    if trait_data[trait].get("contract_msg",None): self.p(trait_data[trait]["contract_msg"])
    
  def del_trait(self,trait):
    if trait in self.traits: self.traits.remove(trait)
      
  def die(self,killer=None):
    p=self.get_place()
    self.p("[n] has been slain.")
    if self.encounter: self.encounter.creatures.remove(self)
    if self.party: self.party.leave(self)
    if isinstance(p,Tribe) and self in p.kennel: p.kennel.remove(self)
    elif isinstance(p,Tile) and self in p.pasture: p.pasture.remove(self)
    corpse=spawn_item("Corpse",p)
    if self.carry: 
      (self.carry.x,self.carry.y,self.carry.z) = (p.x,p.y,p.z)
      game_print(self.carry.display()+" falls to the ground.",p.get_chan())
    if self.language!="none": corpse.heat=self.heat
    corpse.owner=self.basename
    corpse.size=self.corpse["size"]
    corpse.gain=self.corpse["gain"]
    if killer and isinstance(killer,Kobold) and killer.tribe:
      if self.faction!="none": killer.tribe.gain_heat(self.heat,self.faction) #there was a really long chain of variables here but it's gone now
      elif killer.z==0 and self.companion: 
        ct=killer.world.find_tile_feature(10,killer,"Elven Sanctuary","special")
        if ct: killer.tribe.gain_heat(self.heat,"Elf")
    for l in self.loot:
      if chance(l[3]): 
        i=spawn_item(l[0],self.get_place(),random.randint(l[1],l[2]))
        game_print(self.display()+" drops "+i.display()+".",p.get_chan())
    inv=list(self.items)
    for i in inv: i.move(p,tumble=True)
    if self.encounter and len(self.encounter.creatures)==0:
      self.encounter.end()
      
  def slave(self,enemy):
    queen=None
    for c in self.encounter.creatures:
      if "Queen" in c.name: 
        queen=c
        break
    if queen and queen.hp<50:
      self.p("[n] feeds some nectar to the Ant Queen.")
      heal=random.randint(5,10)
      queen.hp_gain(heal)
    else:
      self.attack(enemy)
  
  def multisummon(self,enemy):
    summoned=False
    target=enemy.pop(0)
    for x in range(2):
      if chance(40+self.stats["cha"]): 
        if not summoned:
          self.p("[n] calls upon her subjects.")
          summoned=True
        current=[]
        for c in self.encounter.creatures:
          current.append(c.name[-1])
        a=ord("A")
        while chr(a) in current: a+=1
        new=Creature(choice(enemy),self.world,self.encounter)
        new.name=new.basename+" "+chr(a)
        new.add_trait("summoned")
        new.p("[n] has joined the battle.")
    if not summoned: self.attack(target)
  
  def summon(self,enemy):
    self.p("[n] calls for help...")
    if chance(40+self.stats["cha"]): 
      current=[]
      for c in self.encounter.creatures:
        current.append(c.name[-1])
      a=ord("A")
      while chr(a) in current: a+=1
      new=Creature(enemy[1],self.world,self.encounter)
      new.name=new.basename+" "+chr(a)
      new.add_trait("summoned")
      new.p("[n] has joined the battle.")
    else: game_print("Nothing answered the call.",self.get_chan())
  
  def inflict(self,arg):
    msg=arg[2]
    msg=msg.replace("[n]",self.display())
    msg=msg.replace("[t]",arg[0].display())
    arg[0].p(msg)
    if arg[0].has_trait(arg[1]):
      arg[0].p("[n] is already "+trait_data[arg[1]].get("display",arg[1])+".")
    elif arg[0].save(trait_data[arg[1]]["save_stat"])<trait_data[arg[1]]["save"]:
      arg[0].p("[n] is "+trait_data[arg[1]].get("display",arg[1])+"!")
      arg[0].add_trait(arg[1])
    else:
      arg[0].p("[n] resists.")
  
  def charge(self,target):
    if self.attack(target):
      self.inflict([target,"stunned","[n] collides with [t] at full force!"])
      target.hp_tax(3,"Killed by "+self.display(),self,self.dmgtype)
  
  def cure(self,target):
    worst=None
    for c in self.encounter.creatures:
      if not worst or c.hp<worst.hp: worst=c
    if not worst: return self.attack(target)
    self.p("[n] casts Cure Wounds!")
    worst.hp_gain(droll(1,8)+self.smod("wis"))
  
  def smite(self,target):
    if self.attack(target):
      target.p("[n] is stricken with holy fury!")
      target.hp_tax(droll(1,8),"Killed by "+self.display(),self,"radiant")
  
  def flamewave(self,target):
    self.p("[n] casts Flame Wave!")
    for t in target.party.members:
      dmg=droll(3,8)
      if t.save("dex")>=10+self.smod("int"): dmg=math.ceil(dmg/2)
      t.hp_tax(dmg,"Killed by "+self.display(),self,"fire")
  
  def attack_multi(self,target):
    for x in range(int(target[1])): self.attack(target[0])
  
  def attack_mark(self,target):
    for k in target.party.members:
      if k.has_trait("marked"): target=k
    target.add_trait("marked")
    self.attack(target)
  
  def attack(self,target):
    guard=False
    if isinstance(target,Kobold):
      if target.age<6 and chance(95):
        adults=[]
        for k in target.party.k_members:
          if k.age>=6: adults.append(k)
        tank=choice(adults)
        if tank:
          tank.p("[n] moves to protect "+target.display()+" from harm!")
          target=tank
    if target.guardian: 
      target.p(target.guardian.display()+" moves to protect [n] from harm!")
      target=target.guardian
      guard=True
    return attack_roll(self,target,guarding=guard)
    