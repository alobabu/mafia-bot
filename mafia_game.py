import random
import time
from collections import defaultdict

class Player:
    def __init__(self, name, role):
        self.name = name
        self.role = role
        self.alive = True
        self.protected = False
        self.blocked = False
        self.visited = None
        self.has_healed_self = False
        self.special_block = False
        self.votes = 0
        self.protected_target = None
        self.is_lucky = role == "Счастливчик"
        self.lucky_attacks = 0
        self.has_exploded = False
        self.vote_weight = 2 if role == "Мэр" else 1
        self.protected_by_lawyer = False
        self.has_protected_self = False if role == "Адвокат" else None
        self.last_killed_by_maniac = None
        self.marked_by_arsonist = False
        self.disguised_as = None
        self.checked_with_commissioner = False
        self.werewolf_converted = False
        self.mag_pardoned = False
        self.is_afraid = False
        self.known_roles = set() if role == "Журналист" else None
        self.is_arsonist = role == "Поджигатель"
        self.is_maniac = role == "Маньяк"
        self.is_suicidal = role == "Самоубийца"
        self.is_swindler = role == "Аферист"

    def __str__(self):
        status = " ⚰️" if not self.alive else " 🛡️" if self.protected else ""
        return f"{self.name} ({self.role}){status}"

class MafiaGame:
    def __init__(self, player_names):
        if len(player_names) < 4:
            raise ValueError("Для игры нужно минимум 4 игрока")
        
        roles = self._assign_roles(len(player_names))
        self.players = [Player(name, role) for name, role in zip(player_names, roles)]
        self.day_number = 0
        self.night_deaths = []
        self.arsonist_victims = []
        self.stukach_reveal = None
        self.mag_choices = []
        self.last_killed_by = None

    def _assign_roles(self, player_count):
        base_roles = [
            "Мафия", "Комиссар", "Доктор", "Дон", "Сержант",
            "Любовница", "Бомж", "Мэр", "Счастливчик",
            "Камикадзе", "Мирный житель", "Адвокат", "Убийца"
        ]
        
        extra_roles = [
            "Маньяк", "Поджигатель", "Аферист",
            "Стукач", "Маг", "Оборотень"
        ]
        
        roles = base_roles + extra_roles[:max(0, player_count - len(base_roles))]
        random.shuffle(roles)
        return roles[:player_count]

    def get_alive_players(self):
        return [p for p in self.players if p.alive]

    def get_players_by_role(self, role):
        return [p for p in self.players if p.role == role and p.alive]

    def reset_protections(self):
        for player in self.players:
            player.protected = False
            player.blocked = False
            player.visited = None
            if player.role == "Счастливчик":
                player.lucky_attacks = 0

    def reset_votes(self):
        for player in self.players:
            player.votes = 0

    def select_player(self, prompt, player_list=None, excluded_roles=None, include_self=False):
        if player_list is None:
            player_list = self.get_alive_players()
        
        if excluded_roles:
            player_list = [p for p in player_list if p.role not in excluded_roles]
        
        print(prompt)
        for i, p in enumerate(player_list):
            print(f"{i + 1}. {p.name}")
        
        while True:
            try:
                choice = int(input("Номер игрока: ")) - 1
                if 0 <= choice < len(player_list):
                    return player_list[choice]
                print("Некорректный номер, попробуйте снова")
            except ValueError:
                print("Введите число!")

    def check_lucky_survival(self, target, attacker_role):
        if target.role != "Счастливчик":
            return False
            
        target.lucky_attacks += 1
        
        if target.lucky_attacks == 1:
            print(f"{target.name} (Счастливчик) везучий! Первая атака {attacker_role} не смогла его убить!")
            return True
        elif target.lucky_attacks >= 2:
            if target.protected:
                print(f"{target.name} (Счастливчик) снова везучий! Защита спасает его от {attacker_role}!")
                return True
            else:
                print(f"{target.name} (Счастливчик) исчерпал свою удачу! {attacker_role} убивает его!")
                return False
        return False

    def doctor_night_action(self):
        doctor = next((p for p in self.players if p.role == "Доктор" and p.alive), None)
        if not doctor:
            return

        print(f"\nДоктор {doctor.name}, выбери, кого защитить:")
        alive_players = self.get_alive_players()
        
        for i, p in enumerate(alive_players):
            if p == doctor and not doctor.has_healed_self:
                print(f"{i + 1}. {p.name} (себя)")
            else:
                print(f"{i + 1}. {p.name}")
        
        while True:
            try:
                choice = int(input("Номер игрока: ")) - 1
                if 0 <= choice < len(alive_players):
                    target = alive_players[choice]
                    
                    if target == doctor:
                        if doctor.has_healed_self:
                            print("Вы уже лечили себя в этой игре! Выберите другого игрока.")
                            continue
                        doctor.has_healed_self = True
                    
                    target.protected = True
                    print(f"Доктор защитил {target.name}!")
                    break
                print("Некорректный номер, попробуйте снова")
            except ValueError:
                print("Введите число!")

    def commissioner_night_action(self):
        commissioner = next((p for p in self.players if p.role == "Комиссар" and p.alive), None)
        if not commissioner or commissioner.blocked:
            return

        print(f"\nКомиссар {commissioner.name}, выбери действие:")
        print("1. Проверить игрока")
        print("2. Выстрелить в подозреваемого")
        
        action = input("Выбор (1-2): ")
        
        if action == "1":
            target = self.select_player("Выбери игрока для проверки:", excluded_roles=["Убийца"])
            
            lawyer = next((p for p in self.players 
                         if p.role == "Адвокат" and p.alive and p.protected_target == target), None)
            
            if target.role == "Убийца" or lawyer:
                print(f"Результат проверки: {target.name} - Мирный житель")
            else:
                print(f"Результат проверки: {target.name} - {target.role}")
                
        elif action == "2":
            target = self.select_player("Выбери цель для выстрела:", excluded_roles=["Убийца"])
            
            if target.role == "Убийца":
                print("Вы не можете убить Убийцу! Выстрел обращается против вас!")
                commissioner.alive = False
                self.night_deaths.append(commissioner)
            elif target.role == "Счастливчик" and self.check_lucky_survival(target, "Комиссара"):
                return
            else:
                target.alive = False
                self.night_deaths.append(target)
                print(f"Комиссар застрелил {target.name}!")

    def sergeant_night_action(self):
        sergeant = next((p for p in self.players if p.role == "Сержант" and p.alive), None)
        if not sergeant:
            return
            
        commissioner_alive = any(p.role == "Комиссар" and p.alive for p in self.players)
        
        if not commissioner_alive:
            sergeant.role = "Комиссар"
            print(f"\nСержант {sergeant.name} теперь Комиссар Каттани!")
            self.commissioner_night_action()
        else:
            print(f"\nСержант {sergeant.name} наблюдает за действиями Комиссара...")

    def mistress_night_action(self):
        mistress = next((p for p in self.players if p.role == "Любовница" and p.alive), None)
        if not mistress:
            return

        target = self.select_player(
            f"\nЛюбовница {mistress.name}, выбери, кого посетить:",
            excluded_roles=["Убийца"]
        )
        
        target.blocked = True
        print(f"Любовница посетила {target.name}! Он не сможет действовать этой ночью.")
        
        if target.role == "Дон":
            target.special_block = True

    def bum_night_action(self):
        bum = next((p for p in self.players if p.role == "Бомж" and p.alive), None)
        if not bum:
            return

        target = self.select_player(f"\nБомж {bum.name}, выбери, к кому пойти за бутылкой:")
        bum.visited = target
        print(f"Бомж пошел к {target.name}... Увидимся утром!")

    def mafia_night_action(self):
        mafia = self.get_players_by_role("Мафия") + self.get_players_by_role("Дон")
        if not mafia:
            return

        print(f"\nМафия, выбери, кого убить:")
        don = next((p for p in mafia if p.role == "Дон"), mafia[0])
        
        if don.blocked and not don.special_block:
            print("Дон заблокирован Любовницей и не может действовать!")
            return

        target = self.select_player("Выбери цель:", excluded_roles=["Убийца", "Мафия", "Дон"])
        
        if target.role == "Счастливчик" and self.check_lucky_survival(target, "Мафии"):
            return
        
        if target.role == "Камикадзе":
            if target.protected:
                print(f"Камикадзе {target.name} под защитой доктора и не может быть активирован!")
                return
                
            target.alive = False
            self.night_deaths.append(target)
            print(f"Камикадзе {target.name} активирован! Он выберет жертву утром.")
            return
        
        if target.protected:
            print(f"Мафия выбрала убить {target.name}, но он был под защитой!")
        else:
            target.alive = False
            self.night_deaths.append(target)
            print(f"Мафия убила {target.name}!")
            
            if target.visited and target.visited.role == "Бомж":
                print(f"Бомж {target.visited.name} видел Дона!")

    def maniac_night_action(self):
        maniac = next((p for p in self.players if p.role == "Маньяк" and p.alive), None)
        if not maniac or maniac.blocked:
            return

        print(f"\nМаньяк {maniac.name}, выбери жертву:")
        targets = [p for p in self.get_alive_players() 
                 if p != maniac and p.role != "Маг" and p != maniac.last_killed_by_maniac]
        
        if not targets:
            print("Нет подходящих целей для маньяка")
            return
            
        target = self.select_player("Выбери жертву:", targets)
        
        if target.role == "Счастливчик" and self.check_lucky_survival(target, "Маньяка"):
            maniac.last_killed_by_maniac = target
            return
        
        if target.role == "Камикадзе":
            print("Маньяк попытался убить Камикадзе и погиб сам!")
            maniac.alive = False
            target.alive = False
            self.night_deaths.extend([maniac, target])
            return
            
        if target.protected:
            print(f"Маньяк не смог убить {target.name} - цель под защитой!")
        else:
            target.alive = False
            self.night_deaths.append(target)
            print(f"Маньяк убил {target.name}!")
            maniac.last_killed_by_maniac = target
            
        don_kill = next((p for p in self.night_deaths if p.role == "Дон"), None)
        if don_kill and don_kill == target:
            print("Дон и Маньяк одновременно атаковали одну цель!")

    def arsonist_night_action(self):
        arsonist = next((p for p in self.players if p.role == "Поджигатель" and p.alive), None)
        if not arsonist or arsonist.blocked:
            return

        print(f"\nПоджигатель {arsonist.name}, выбери жертву:")
        targets = [p for p in self.get_alive_players() 
                 if p != arsonist and p.role != "Убийца" and not p.marked_by_arsonist]
        
        target = self.select_player("Выбери жертву:", targets)
        
        if len(self.arsonist_victims) >= 2 and target.role == "Счастливчик":
            if self.check_lucky_survival(target, "Поджигателя"):
                return
        
        target.marked_by_arsonist = True
        self.arsonist_victims.append(target)
        print(f"{target.name} помечен для поджога!")
        
        if len(self.arsonist_victims) >= 3:
            print("\nПоджигатель готов совершить поджог!")
            choice = input("Хотите активировать поджог сейчас? (да/нет): ").lower()
            if choice == 'да':
                arsonist.alive = False
                for victim in self.arsonist_victims:
                    if victim.protected:
                        print(f"{victim.name} спасся от поджога благодаря защите!")
                    else:
                        victim.alive = False
                        self.night_deaths.append(victim)
                self.night_deaths.append(arsonist)
                print("Поджигатель совершил массовый поджог!")

    def swindler_night_action(self):
        swindler = next((p for p in self.players if p.role == "Аферист" and p.alive), None)
        if not swindler or swindler.blocked:
            return

        print(f"\nАферист {swindler.name}, выбери игрока для маскировки:")
        targets = [p for p in self.get_alive_players() if p != swindler]
        
        target = self.select_player("Выбери игрока для маскировки:", targets)
        swindler.disguised_as = target
        print(f"Аферист теперь маскируется под {target.name}!")

    def stukach_night_action(self):
        stukach = next((p for p in self.players if p.role == "Стукач" and p.alive), None)
        if not stukach or stukach.blocked:
            return

        print(f"\nСтукач {stukach.name}, выбери игрока для проверки:")
        target = self.select_player("Выбери игрока для проверки:", self.get_alive_players())
        
        commissioner = next((p for p in self.players if p.role == "Комиссар" and p.alive), None)
        if commissioner and commissioner.visited == target:
            self.stukach_reveal = target
            print(f"Стукач и Комиссар проверили одного и того же игрока - {target.name}!")
        else:
            print("Комиссар не проверял этого игрока этой ночью")

    def mag_night_interaction(self):
        mag = next((p for p in self.players if p.role == "Маг" and p.alive), None)
        if not mag:
            return
            
        attackers = []
        for p in self.players:
            if p.role in ["Дон", "Маньяк", "Комиссар"] and p.visited == mag and p.alive:
                attackers.append(p)
                
        if attackers:
            print(f"\nМаг {mag.name}, выберите действие:")
            for i, attacker in enumerate(attackers):
                print(f"{i+1}. Помиловать {attacker.name} ({attacker.role})")
                print(f"{i+1}. Убить {attacker.name} ({attacker.role})")
                
            choices = []
            for attacker in attackers:
                choice = input(f"Помиловать (п) или убить (у) {attacker.name}?: ").lower()
                choices.append((attacker, choice == 'у'))
                
            for attacker, kill in choices:
                if kill:
                    attacker.alive = False
                    self.night_deaths.append(attacker)
                    print(f"Маг убил {attacker.name}!")
                else:
                    print(f"Маг помиловал {attacker.name}")

    def werewolf_conversion(self):
        werewolf = next((p for p in self.players if p.role == "Оборотень" and not p.alive and not p.werewolf_converted), None)
        if not werewolf:
            return
            
        killer = self.last_killed_by
        if killer:
            if killer.role == "Мафия" or killer.role == "Дон":
                werewolf.role = "Мафия"
                werewolf.alive = True
                werewolf.werewolf_converted = True
                print(f"Оборотень {werewolf.name} воскрес как Мафия!")
            elif killer.role == "Комиссар":
                werewolf.role = "Сержант"
                werewolf.alive = True
                werewolf.werewolf_converted = True
                print(f"Оборотень {werewolf.name} воскрес как Сержант!")
            elif killer.role in ["Маньяк", "Убийца"]:
                print(f"Оборотень {werewolf.name} окончательно убит {killer.role}ом!")
            elif killer.role == "Дон" and any(p.role == "Комиссар" and p.visited == werewolf for p in self.players):
                print(f"Оборотень {werewolf.name} убит одновременно Доном и Комиссаром!")

    def kamikaze_trigger(self, executed):
        if executed.role == "Камикадзе" and not executed.protected:
            print(f"\n{executed.name} был камикадзе! Он может забрать с собой одного игрока")
            
            targets = [p for p in self.get_alive_players() 
                     if p != executed and p.role not in ["Камикадзе", "Убийца"]]
            
            if targets:
                target = self.select_player("Выбери цель для самоуничтожения:", targets)
                target.alive = False
                print(f"Камикадзе забрал с собой {target.name} ({target.role})!")
            else:
                print("Нет подходящих целей для Камикадзе")

    def check_suicide_win(self, executed):
        if executed.role == "Самоубийца":
            print(f"{executed.name} добился своей цели - его казнили!")

    def mayor_day_action(self):
        mayor = next((p for p in self.players if p.role == "Мэр" and p.alive), None)
        if mayor:
            print(f"\nМэр {mayor.name} имеет двойной голос на этом голосовании!")
            return mayor

    def lawyer_night_action(self):
        lawyer = next((p for p in self.players if p.role == "Адвокат" and p.alive), None)
        if not lawyer or lawyer.blocked:
            return

        print(f"\nАдвокат {lawyer.name}, выбери кого защитить:")
        targets = [p for p in self.get_alive_players() 
                  if p.role in ["Мафия", "Дон", "Убийца", "Журналист"] or p == lawyer]
        
        for i, p in enumerate(targets):
            if p == lawyer and not lawyer.has_protected_self:
                print(f"{i + 1}. {p.name} (себя)")
            else:
                print(f"{i + 1}. {p.name}")

        choice = int(input("Номер игрока: ")) - 1
        target = targets[choice]
        
        if target == lawyer:
            lawyer.has_protected_self = True
        target.protected_by_lawyer = True
        lawyer.protected_target = target
        print(f"Адвокат защитил {target.name}!")

    def killer_night_action(self):
        killer = next((p for p in self.players if p.role == "Убийца" and p.alive), None)
        if not killer or (killer.blocked and not killer.special_block):
            return

        print(f"\nУбийца {killer.name}, выбери цель:")
        targets = [p for p in self.get_alive_players() 
                  if p.role in ["Бомж", "Доктор", "Любовница", "Сержант", "Камикадзе", "Маньяк", "Поджигатель"]]
        
        target = self.select_player("Выбери жертву:", targets)
        
        if target.role == "Комиссар":
            killer.alive = False
            self.night_deaths.append(killer)
            print("Убийца попытался убить Комиссара и погиб сам!")
        elif target.protected:
            print(f"Убийца не смог убить {target.name} - цель под защитой!")
        else:
            target.alive = False
            self.night_deaths.append(target)
            print(f"Убийца устранил {target.name} ({target.role})!")

    def night_phase(self):
        print("\n=== Ночь ===")
        self.reset_protections()
        self.night_deaths = []
        self.stukach_reveal = None

        # Порядок действий:
        self.mistress_night_action()    # Любовница
        self.doctor_night_action()      # Доктор
        self.lawyer_night_action()      # Адвокат
        self.mafia_night_action()       # Мафия/Дон
        self.killer_night_action()      # Убийца
        self.maniac_night_action()      # Маньяк
        self.commissioner_night_action()# Комиссар
        self.sergeant_night_action()    # Сержант
        self.bum_night_action()         # Бомж
        self.stukach_night_action()     # Стукач
        self.swindler_night_action()    # Аферист
        self.arsonist_night_action()    # Поджигатель
        self.mag_night_interaction()    # Маг
        self.werewolf_conversion()      # Оборотень

    def morning_announcement(self):
        print("\n=== Утро ===")
        if not self.night_deaths:
            print("Этой ночью никто не погиб!")
        else:
            for victim in self.night_deaths:
                print(f"Игрок {victim.name} ({victim.role}) был убит ночью! ⚰️")
        
        if self.stukach_reveal:
            print(f"Стукач и Комиссар проверили {self.stukach_reveal.name} - это {self.stukach_reveal.role}!")

    def day_phase(self):
        self.day_number += 1
        print(f"\n=== День {self.day_number} ===")
        
        # Проверка афериста у мэра
        mayor = next((p for p in self.players if p.role == "Мэр" and p.alive), None)
        swindler = next((p for p in self.players if p.role == "Аферист" and p.alive), None)
        
        if mayor and swindler and swindler.disguised_as == mayor:
            print(f"⚠️ Аферист {swindler.name} маскируется под мэра!")
            swindler.vote_weight = 2

        # Голосование
        print("\nГолосование за казнь:")
        votes = defaultdict(int)
        for voter in self.get_alive_players():
            if voter.blocked and voter.role != "Убийца":
                print(f"{voter.name} заблокирован и не может голосовать!")
                continue
                
            target = self.select_player(f"{voter.name}, за кого голосуете:", include_self=True)
            votes[target.name] += voter.vote_weight
            print(f"{voter.name} голосует против {target.name} (вес: {voter.vote_weight})")

        # Подсчет голосов
        if votes:
            max_votes = max(votes.values())
            candidates = [name for name, count in votes.items() if count == max_votes]
            
            if len(candidates) > 1:
                print("\nНесколько игроков получили одинаковое количество голосов!")
            else:
                executed_name = candidates[0]
                executed = next(p for p in self.get_alive_players() if p.name == executed_name)
                
                if executed.protected_by_lawyer:
                    print(f"{executed.name} под защитой адвоката и не может быть казнен!")
                else:
                    executed.alive = False
                    print(f"{executed.name} казнён по результатам голосования!")
                    
                    if executed.role == "Камикадзе":
                        self.kamikaze_trigger(executed)
                    elif executed.role == "Самоубийца":
                        self.check_suicide_win(executed)

        self.reset_votes()
        self.reset_protections()

    def check_win_condition(self):
        mafia = self.get_players_by_role("Мафия") + self.get_players_by_role("Дон")
        civilians = [p for p in self.get_alive_players() if p.role not in ["Мафия", "Дон", "Маньяк", "Поджигатель", "Аферист", "Убийца"]]
        neutrals = [p for p in self.get_alive_players() if p.role in ["Маньяк", "Поджигатель", "Аферист", "Убийца"]]

        if not mafia and not any(p.role == "Убийца" for p in self.get_alive_players()):
            print("\nМирные жители победили! 🎉")
            return True
        if len(mafia) >= len(civilians) + len(neutrals):
            print("\nМафия победила! 🔪")
            return True
        if len(neutrals) == 1 and neutrals[0].role == "Маньяк":
            print("\nМаньяк победил, убив всех! 😈")
            return True
        if len(self.get_alive_players()) == 1 and self.get_alive_players()[0].role == "Аферист":
            print("\nАферист победил, пережив всех! 🎭")
            return True
        return False

    def start_game(self):
        print("Игра начинается! Роли распределены.")
        time.sleep(1)
        
        # Для тестирования - показать роли
        for p in self.players:
            print(f"{p.name}: {p.role}")
        time.sleep(3)
        
        while True:
            self.night_phase()
            self.morning_announcement()
            if self.check_win_condition():
                break

            self.day_phase()
            if self.check_win_condition():
                break

if __name__ == "__main__":
    try:
        players = input("Введите имена игроков через запятую: ").split(',')
        players = [name.strip() for name in players if name.strip()]
        
        if len(players) < 4:
            print("Ошибка: для игры нужно минимум 4 игрока")
        else:
            game = MafiaGame(players)
            game.start_game()
    except Exception as e:
        print(f"Произошла ошибка: {e}")
