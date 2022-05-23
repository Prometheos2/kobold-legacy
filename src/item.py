import math
import random

import discord

from encounter import Encounter
from kobold import Kobold
from tribe import Tribe

from ..kobold import (DIR_FULL, action_queue, chance, check_req, choice,
                      console_print, describe_quality, find_research,
                      game_print, get_dir, get_tri_distance, item_data,
                      landmark_data, liquid_data, spawn_item, spell_data)


class Item:
  def __init__(self,name,num=1):
    for i in item_data:
      if i["name"]=="Default":
        for k in i.keys(): setattr(self,k,i[k])
      if i["name"]==name:
        for k in i.keys(): setattr(self,k,i[k])
        break
    self.num=num
    if self.num>self.stack: self.num=max(self.stack,1)
    self.quality=0
    self.attunelevel=0
    self.base_durability=self.durability
    self.dura_loss=1
    self.place=None
    self.kobold=None
    self.owner=None
    self.liquid=None
    self.contains=None
    self.bound=None
    self.inert=False
    self.liquid_units=0
    self.note=""
    self.map={}
    self.sold=False
    
  @property
  def max_durability(self):
    return math.floor(self.base_durability*(1+(self.quality/10)))
    
  @property
  def realvalue(self):
    dura=1
    if self.durability>0 and self.max_durability>0: dura=(self.durability/self.max_durability)
    v=int(self.value*dura*self.num/self.dura_loss)
    if self.liquid: v+=self.liquid_units*liquid_data[self.liquid].get("value",0)
    return v
    
  def set_quality(self,q):
    if self.noquality or self.stack>1: return
    self.quality=q
    self.value=int(self.value*(1+(q/5)))
    self.durability=self.max_durability
    
  def spawn_quality(self):
    if self.noquality or self.stack>1: return
    qv=random.randint(1,100)
    if qv==100: q=4
    elif qv>97: q=3
    elif qv>89: q=2
    elif qv>75: q=1
    elif qv>50: q=0
    elif qv>25: q=-1
    elif qv>11: q=-2
    elif qv>3: q=-3
    else: q=-4
    self.set_quality(q)
  
  def display(self):
    d=self.name
    if isinstance(self.place,Kobold):
      if self.place.equip==self: d="[E]"+d
      else:
        for w in self.place.worns:
          if self.place.worns[w]==self: d="["+w+"]"+d
    if self.quality!=0: 
      qstr=str(self.quality)
      if self.quality>0: qstr="+"+qstr
      d+="["+qstr+"]"
    if self.note!="":
      if len(self.note)>20: d+=" ("+self.note[:20]+"...)"
      else: d+=" ("+self.note+")"
    if self.num!=1: d+=" x"+str(self.num)
    if self.owner: d+=" ("+str(self.owner)+")"
    if self.school not in ["none","open"] and self.type!="gem": d+=" ("+self.school+" "+str(self.attunelevel)+")"
    if self.inert: d+=" (Inert)"
    if self.type=="container": 
      if self.liquid: d+=" ("+self.liquid
      elif self.contains: d+=" ("+self.contains.display()
      else: d+=" (Empty"
      if self.liquid_capacity>1:
        d+=" "+str(self.liquid_units)+"/"+str(self.liquid_capacity)
      d+=")"
    return d
    
  def examine(self,me,multi=False):
    title=self.name
    d="Location: "
    if isinstance(self.place,Kobold): 
      if self in self.place.worn_items(): d+="Worn by "+self.place.display()
      else: d+=self.place.display()+"'s inventory"
    else: d+="Ground"
    if self.note!="": d+="\nNote: "+self.note
    if self.stack>1: d+="\nAmount: "+str(self.num)+"/"+str(self.stack)
    if self.liquid: d+="\nContains: "+self.liquid+" "+str(self.liquid_units)+"/"+str(self.liquid_capacity)
    if self.school!="none": d+="\nAttunement: "+self.school+" "+str(self.attunelevel)
    if self.type=="corpse":
      d+="\nOwner: "+str(self.owner)
      d+="\nSize (AP cost to butcher): "+str(self.size)
      g=[]
      for y in self.gain: g.append(y[0]+" x"+str(y[1]))
      d+="\nPossible yield: "+", ".join(g)+"\n"
    elif self.kobold:
      d+="\nEgg color: "+self.kobold.color+"\n"
    else: 
      d+="\nQuality: "+describe_quality(self.quality)
      if self.quality>0: d+=" (+"+str(self.quality)+")\n"
      else: d+=" ("+str(self.quality)+")\n"
    if self.durability>0: d+="Durability: "+str(self.durability)+"/"+str(self.max_durability)+"\n"
    d+=self.desc
    if not multi: 
      action_queue.append(["embed",me.get_chan(),discord.Embed(type="rich",title=title,description=d)])
      return d
    else: return discord.Embed(type="rich",title=title,description=d)
    
  def move(self,to,tumble=False):
    if not isinstance(to,Item) and not isinstance(to,list):
      for i in to.items:
        if i.name==self.name:
          stacking=min(i.stack-i.num,self.num)
          self.num-=stacking
          i.num+=stacking
          if self.num<=0:
            self.destroy("Stacked with like item")
            break
    if self.place: 
      if not isinstance(self.place,Item): 
        if self in self.place.items: self.place.items.remove(self)
      else: self.place.contains=None
      if isinstance(self.place,Kobold):
        if self.place.equip==self: self.place.equip=None
        for w in self.place.worns:
          if self.place.worns[w]==self: self.place.worns[w]=None
        if len(self.place.items)>self.place.inv_size and not tumble:
          self.place.p("Some of [n]'s items tumble to the ground.")
          n=len(self.place.items)-self.place.inv_size
          it=list(self.place.items)
          for h in it:
            if self.place.equip==h or h in list(self.place.worns.values()): continue
            h.move(self.place.get_place(),tumble=True)
            n-=1
            if n<=0: break
    if self.num>0: 
      self.place=to
      if isinstance(to,Item): to.contains=self
      elif isinstance(to,list): 
        to.append(self)
        self.place=None
      else: to.items.append(self)
    
  def destroy(self,cause="Unknown"):
    if self.place: 
      if isinstance(self.place,Item): self.place.contains=None
      elif self in self.place.items: self.place.items.remove(self)
      if isinstance(self.place,Kobold):
        if self.place.equip==self: self.place.equip=None
      self.bound=None
      if cause=="Spoiled" and self.rot_into!="none":
        skele=spawn_item(self.rot_into,self.place)
        skele.size=self.size
        skele.owner=self.owner
        sgain=[]
        for g in self.gain:
          for i in item_data:
            if i["name"]==g[0] and not i.get("perishable",False):
              sgain.append(g)
              break
        if len(sgain)>0: skele.gain=sgain
      self.place=None
      console_print(self.display()+" destroyed. Cause: "+cause)
    
  def drink_from(self,k):
    if self.liquid_units<=0 or not self.liquid:
      k.p("The "+self.display()+" is empty.")
      return False
    drank=k.drink(self.liquid)
    if not drank: return False
    self.liquid_units-=1
    if self.liquid_units<=0: 
      self.liquid=None
      k.p("The "+self.display()+" is now empty.")
    return True
    
  def magic_item_use(self,k,msg):
    if chance(max(5,50-((k.skmod("arcana")-self.magic_level)*5))):
      k.p(msg)
      self.inert=True
    if k.skmod("arcana")<self.magic_level: k.gain_xp("arcana",self.magic_level*10)
    
  def use(self,k):
    if k.hp<=0: return False
    if self.inert:
      k.p("The "+self.display()+" is inert and must recharge.")
      return False
    if self.name=="Default":
      k.p("How did you get this?")
      self.destroy("cleaning up the default")
      game_print("A default was discovered by "+k.get_name()+", channel "+k.get_chan(),"exception-log")
      return True
    elif self.type=="container":
      return self.drink_from(k)
    elif self.name=="Thesis":
      if not isinstance(k.get_place(),Tribe):
        k.p("Must be used in a den.")
        return False
      r=find_research(self.note)
      if r["name"] in k.tribe.research:
        k.p(self.note+" is already available for this tribe.")
        return False
      good=check_req(k.tribe,r.get("req",[]),k)
      if good!="good":
        k.p("Cannot install this research: "+good)
        return False
      k.tribe.research.append(r["name"])
      k.p("[n] studies the thesis carefully and works to integrate it into their tribe's way of life. "+self.note+" research has been completed!")
      self.destroy("Knowledge applied")
      return True
    elif self.type=="food":
      if not k.has_trait("fed"):
        k.add_trait("fed")
        k.del_trait("starving")
        ch=self.quality*20
        if chance(abs(ch)):
          if ch>0: self.ap+=1
          else: self.ap-=1
        k.p("[n] chows down on the "+self.display()+" and gains "+str(self.ap)+" AP.")
        for t in self.del_trait: k.del_trait(t)
        for t in self.add_trait: k.add_trait(t)
        for t in self.skill_boost: k.skillboost[t]+=self.skill_boost[t]
        if k.has_trait("stressed") and k.save("wis")+self.ap>=12:
          k.del_trait("stressed")
          k.p("[n] is feeling a lot more relaxed after that.")
        k.ap_gain(self.ap,False)
        if self.ap>10: k.ap+=self.ap-10
        if self.hp<0: k.hp_tax(self.hp*-1,"Dangerous meal",dmgtype="poison")
        else:
          if chance(abs(ch)):
            if ch>0: self.hp+=1
            else: self.hp-=1
          if self.hp>0: k.hp_gain(self.hp)
        if self.mp>0: k.mp_gain(self.mp)
        if self.heat>0: 
          if k.tribe: 
            k.tribe.gain_heat(self.heat)
            k.p("This gruesome act will not go without consequence... The tribe's heat level has increased.")
        self.num-=1
        if self.num<=0: self.destroy("Eaten")
        return True
      else: k.p("[n] has already eaten recently.")
    elif self.name=="Peg Leg":
      if k.has_trait("oneleg"):
        k.del_trait("oneleg")
        k.add_trait("pegleg")
        k.p("[n] installs the peg leg in place of their missing limb. Good as new... sort of.")
        self.destroy("Installed")
      elif k.has_trait("nolegs"):
        if k.has_item("Peg Leg",2):
          k.del_trait("nolegs")
          k.add_trait("doublepegleg")
          k.p("[n] installs the peg legs in place of their missing limbs. Good as new... sort of.")
          k.consume_item("Peg Leg",2)
        else: k.p("Just one of these isn't going to help your situation much.")
      else: k.p("There's no need for this. Yet.")
    elif self.name=="Stone Tablet":
      if self.note=="": k.p("Nothing is written here. Type !write <text> to write something.")
      else: k.p(self.note)
      return True
    elif self.name=="Crude Map":
      self.map_update(k)
      for i in k.items:
        if i.name=="Crude Map" and i!=self:
          self.map_merge(i)
          k.p("[n] copies information from each of their maps to the other.")
      self.map_render(k)
      return True
    elif self.name=="Manacite":
      sp=[]
      if not k.has_trait("manacite"): k.p("[n] presses the Manacite to their forehead, and it begins to glow a magnificent blue...")
      else: 
        k.p("[n] presses the Manacite to their forehead, and it glows brightly... too brightly... it's burning hot! And it's stuck!")
        k.hp_tax(k.max_mp,"Mana burn",dmgtype="force")
        if k.hp<=0:
          self.destroy("Manacite used")
          return True
      for s in spell_data:
        if s["name"] not in k.spells and s["level"]<=(k.skill["sorcery"]/2) and "arcane" in s["spell_class"]: 
          if self.school=="open" or self.school==s["school"]: 
            if s["level"]>=self.attunelevel-1: sp.append(s["name"])
      newspell=choice(sp)
      if newspell:
        if len(k.spells)==0: k.p("[n] has become a mage!")
        k.spells.append(newspell)
        k.p("[n] has learned the "+newspell+" spell!")
      else:
        k.p("[n] feels more experienced with magic!")
        k.gain_xp("arcana",100)
        k.gain_xp("sorcery",100)
      k.mp_gain(k.max_mp)
      k.add_trait("manacite")
      self.destroy("Manacite used")
      return True
    elif self.name=="Charged Mana Cell":
      ma=min(10,math.floor(k.skmod("arcana")/2)+5)
      if len(k.spells)==0 or k.has_trait("manacite"):
        k.p("[n] presses the Mana Cell to their forehead and the blue energy flows through their body... but they are unable to handle it and receive a painful discharge!")
        k.hp_tax(ma,"Mana Burn",dmgtype="force")
      else:
        k.p("[n] presses the Mana Cell to their forehead and the blue energy flows through their body...")
      k.mp_gain(ma)
      if chance(max(5,50-(k.skmod("arcana")*5))): 
        k.p("[n] feels overwhelmed by mana... they'd best not try this again for a while.")
        k.add_trait("manacite")
      k.gain_xp("arcana",10)
      self.destroy("Took in mana")
      spawn_item("Inert Mana Cell",k)
      return True
    elif self.name=="Inert Mana Cell":
      if k.mp_tax(10):
        k.p("[n] presses the Mana Cell between their hands and the blue energy flows from their body into the cell, charging it.")
        self.destroy("Charged")
        spawn_item("Charged Mana Cell",k)
        k.gain_xp("arcana",10)
        return True
      return False
    elif self.name=="Ant Pheromonal Gland":
      place=k.get_place()
      if isinstance(place,Tribe):
        k.p("You do NOT want to use that in the den, trust me on this.")
        return False
      for e in k.world.encounters:
        if e.place==place:
          k.p("Don't be crazy, there are already creatures nearby...")
          return False
      ct=k.world.find_tile_feature(15,k,"Ant Nest","special",gen=True)
      k.p("[n] squeezes the Ant Pheromonal Gland, which emits a strong scent not unlike rotten fruit...")
      if ct:
        dir=get_dir(ct,k)
        if dir!="same": k.p("Ants crawl out of crevasses in the "+dir+" wall and swarm the party!")
        else: k.p("Ants immediately pour out of the nest and engage the party!")
        e=Encounter(k.world,place,random.randint(8,12),k.z,choice(["Worker Ant","Soldier Ant"])) #should spawn 2-3 workers or 1-2 soldiers
        e.start(k.party)
      else: k.p("However, nothing happens.")
      if chance(50):
        k.p("The Ant Pheromonal Gland is depleted.")
        self.destroy("Depleted")
      return True
    elif self.name=="Tin Rod":
      ct=k.world.find_tile_feature(10,k,"Raw Manacite","resources",gen=True)
      k.p("[n] holds out the Tin Rod and feels out the vibrations within...")
      if ct:
        dir=get_dir(ct,k)
        if dir!="same": k.p("The rod pulls toward the "+dir+".")
        else: k.p("The rod is hot to the touch!")
        self.magic_item_use(k,"The Tin Rod suddenly overheats. It's impossible to hold now; best to wait for it to cool off...")
      else: k.p("The rod is completely still.")
      return True
    elif self.name=="Flare Wand":
      tribes=[]
      for t in k.world.tribes:
        if get_tri_distance(k.x,k.y,t.x,t.y)<15: tribes.append(t)
      if len(tribes)>0:
        k.p("[n] holds up the Flare Wand, which begins to spark and glow a brilliant red. Yellow streaks fly off of it and travel into the distance.")
        for t in tribes: 
          dstr=""
          if k.x>t.x: dstr+=str(k.x-t.x)+"-east "
          elif k.x<t.x: dstr+=str(t.x-k.x)+"-west "
          if k.y>t.y: dstr+=str(k.y-t.y)+"-south"
          elif k.y<t.y: dstr+=str(t.y-k.y)+"-north"
          if dstr!="": game_print("A puff of smoke materializes in the middle of the den, showing brief visions of "+k.display()+". Everyone who witnesses is magically made aware of the signal's relative origin: "+dstr,t.get_chan())
        self.magic_item_use(k,"The Flare Wand flickers out and becomes cold to the touch.")
      else: k.p("The flare wand is warm but unresponsive. There must not be anyone nearby to receive the signal...")
      return True
    elif self.name=="Crystal Ball":
      k.p("[n] peers into the crystal ball...")
      ct=None
      if chance(50):
        ct=choice(k.world.tribes)
        if ct and len(ct.kobolds)>0: 
          other=choice(ct.kobolds)
          k.p("[n] sees a community of kobolds... about "+str(len(ct.kobolds))+" of them. They hear a name: "+other.get_name()+".")
          other.p("[n] gets a strange feeling, like they're being watched.")
        else: k.p("[n] sees a kobold den, devoid of any activity...")
      else:
        ct=k.world.find_tile_feature(20,k,"Goblin Camp","special",gen=False)
        if ct: k.p("[n] sees a camp full of goblins.")
        else: k.p("The crystal ball is hazy... it's impossible to make out anything.")
      if ct:
        dir=get_dir(ct,k)
        if dir!="same": k.p("[n] senses that this place is somewhere to the "+dir+".")
        else: k.p("[n] sees themselves in the vision as well, holding the crystal ball.")
      self.magic_item_use(k,"The Crystal Ball suddenly makes a noise like shattering glass and goes dim. It's become inert.")
    else: k.p("The "+self.display()+" cannot be used.")
    return False
    
  def lower_durability(self,am=1):
    self.durability-=am*self.dura_loss
    if self.durability<=0:
      game_print("The "+self.display()+" breaks!",self.place.get_chan())
      if isinstance(self.place,Kobold) and self==self.place.equip:
        self.place.add_trait("tool_broke")
      self.destroy("Out of durability")
  
  def hatch(self):
    if not self.kobold: 
      if self.place:
        t=None
        if isinstance(self.place,Kobold): t=self.place.tribe
        elif isinstance(self.place,Tribe): t=self.place
        else: #see which kobolds are present, pick one of them
          bolds=[]
          for k in self.place.world.kobold_list:
            if k.tribe and k.get_place()==self.place: bolds.append(k)
          t=choice(bolds).tribe
        if t: self.kobold=Kobold(t)
        else: self.kobold=Kobold(self.place.world.tribes[0])
        if not isinstance(t,Tribe): self.kobold.tribe=None
        self.kobold.age=0
        self.kobold.random_stats()
        for st in self.kobold.s: self.kobold.s[st]=0
        self.kobold.hp=self.kobold.max_hp
      else:
        self.destroy("Bad egg")
        return
    if not self.place:
      console_print("Can't place hatchling kobold "+self.kobold.name+" of tribe "+str(self.kobold.tribe.id),hp=True)
    else:
      self.kobold.x=self.place.x
      self.kobold.y=self.place.y
      self.kobold.z=self.place.z
      self.kobold.ap=0
      if isinstance(self.place,Kobold): p=self.place.get_place()
      else: p=self.place
      if isinstance(p,Tribe): 
        p.add_bold(self.kobold)
        self.kobold.tribe=p
      elif isinstance(self.place,Kobold): 
        self.place.party.join(self.kobold)
        self.kobold.tribe=self.place.tribe
    self.kobold.p("[n] has hatched!")
    if self.kobold not in self.kobold.world.kobold_list: self.kobold.world.kobold_list.append(self.kobold)
    self.destroy("Hatched")
    
  def butcher(self,k):
    ch=40+(k.smod("wis")*2)+(k.skmod("survival")*2)
    ch+=k.equip_bonus("butchering")
    p=k.get_place()
    if isinstance(p,Tribe) and "Butcher Table" in p.buildings: 
      ch-=(self.size-1)*5
      ch*=2
    else: ch-=(self.size-1)*15
    got={}
    missed=0
    hit=0
    for y in self.gain:
      for x in range(y[1]):
        if chance(ch+missed): 
          if y[0] in got: got[y[0]]+=1
          else: got[y[0]]=1
        else: 
          missed+=1
          if y[0]=="Raw Meat":
            if "Chunked Meat" in got: got["Chunked Meat"]+=1
            else: got["Chunked Meat"]=1
    for i in got: 
      spawn_item(i,k.get_place(),got[i])
      hit+=got[i]
    if hit==0: k.p("[n]'s hack butcher job left nothing usable in its wake.")
    elif missed>0: k.p("[n] butchered the corpse, but destroyed "+str(missed)+" materials.")
    else: 
      k.p("[n] butchered the corpse with surgical precision.")
      hit*=2
    if self.heat>0 and k.tribe: 
      k.tribe.gain_heat(self.heat)
      k.p("This gruesome act will not go without consequence... The tribe's heat level has increased.")
    self.destroy("Butchered")
    return hit
    
  def map_merge(self,other):
    combined={}
    for m in self.map: combined[m]=dict(self.map[m])
    for m in other.map: combined[m]=dict(other.map[m])
    for m in combined:
      if m in self.map and m in other.map:
        if self.map[m]["symbol"]!="O": combined[m]["symbol"]=self.map[m]["symbol"]
        if other.map[m]["symbol"]!="O": combined[m]["symbol"]=other.map[m]["symbol"]
        for d in DIR_FULL: 
          if self.map[m][d] and other.map[m][d]: combined[m][d]=True
          else: combined[m][d]=False
    self.map=dict(combined)
    other.map=dict(combined)
  
  def map_update(self,k):
    m=str(k.x)+","+str(k.y)+","+str(k.z)
    if m not in self.map: self.map[m]={"symbol":"O","x":k.x,"y":k.y,"z":k.z}
    t=k.get_place()
    if isinstance(t,Tribe): t=k.world.get_tile(t.x,t.y,t.z)
    if t.get_tribe(): self.map[m]["symbol"]="T"
    elif t.camp: self.map[m]["symbol"]="C"
    elif len(t.special)>0: self.map[m]["symbol"]=landmark_data[t.special[0]]["mark"]
    else: self.map[m]["symbol"]="O"
    for d in DIR_FULL: self.map[m][d]=t.blocked[d]
    k.p("[n] updates their "+self.name+".")
    
  def map_render(self,k):
    lowx=9999
    lowy=9999
    highx=-9999
    highy=-9999
    r={}
    for m in self.map:
      if self.map[m]['x']<lowx: lowx=self.map[m]['x']
      if self.map[m]['x']>highx: highx=self.map[m]['x']
      if self.map[m]['y']<lowy: lowy=self.map[m]['y']
      if self.map[m]['y']>highy: highy=self.map[m]['y']
    ycount=lowy
    msg=[]
    row=[]
    for a in range((((highx-lowx)+1)*2)+1): row.append(" ")
    for b in range((((highy-lowy)+1)*2)+1): msg.append(list(row))
    #console_print("msg and row: "+str(len(msg))+","+str(len(row)))
    #console_print("lowx and y: "+str(lowx)+","+str(lowy))
    for m in self.map:
      xx=((self.map[m]['x']-lowx)*2)+1
      yy=((self.map[m]['y']-lowy)*2)+1
      #console_print("xx and yy: "+str(xx)+","+str(yy))
      if k.x==self.map[m]['x'] and k.y==self.map[m]['y']: msg[yy][xx]="@"
      else: msg[yy][xx]=self.map[m]["symbol"]
      if not self.map[m]["w"]: msg[yy][xx-1]="-"
      if not self.map[m]["n"]: msg[yy-1][xx]="|"
      if not self.map[m]["e"]: msg[yy][xx+1]="-"
      if not self.map[m]["s"]: msg[yy+1][xx]="|"
    lines=[]
    for y in msg:
      lines.append("".join(y))
    k.p("```"+"\n".join(lines)+"```")
    