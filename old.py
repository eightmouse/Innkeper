import json

def main():
    #Title
    print('WoW Tracker - Version 0.5')

    def save_data(characters):
        with open('characters.json', 'w') as f:
            json.dump(characters, f, indent=4)
    
    def load_data():
        try:
            with open('characters.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    #Data
    characters = load_data()

    while True:
        #Menu Options
        print('1. Add Character\n2. View Characters\n3. Exit:\n4. Check Activities\n5. Reset Weeklies')
        choice = input('Choose an option: ')

        #Close Program
        if choice == '3':
            save_data(characters)
            print('Data saved. Exiting...')
            break

        #Add Character
        elif choice == '1':
            name = input('Character name: ')
            level = input('Character level: ')
            realm = input('Realm name: ')
            characters.append(
                {
                    'name': name,
                    'level': level,
                    'realm': realm,
                    'activities': 
                    {
                        'Raid': False,
                        'Mythic+': False,
                        'World Boss': False
                    }
                })

        #View Characters
        elif choice == '2':
            print('Characters:')
            if not characters:
                print('No characters added.')
            for char in characters:
                print(f'- {char["name"]} (Level {char["level"]}) on {char["realm"]}')

                #Activities
                for activity, done in char['activities'].items():
                    if done:
                        mark = "[x]"
                    else:
                        mark = "[ ]"
                    print(f'  {mark} {activity}')

        #Check Activities
        elif choice == '4':
            if not characters:
                print('No characters to check activities for.')
            else:
                for i, char in enumerate(characters):
                    print(f'{i + 1}. {char["name"]}')
                choice = int(input('Which character?: '))
                selected_char = characters[choice - 1]

                #Toggle Activities
                for i, activity in enumerate(selected_char['activities']):
                    done = selected_char['activities'][activity]
                    mark = "[x]" if done else "[ ]"
                    print(f'{i + 1}. {mark} {activity}')
                activity_choice = int(input('Toggle which activity?: '))
                activity_name = list(selected_char['activities'].keys())[activity_choice - 1]
                selected_char['activities'][activity_name] = True
                print(f'Checked {activity_name} for {selected_char["name"]}')

        #Reset Weeklies
        elif choice == '5':  
            for char in characters: 
                for activity in char['activities']:
                    char['activities'][activity] = False
            print('All weeklies reset.')

if __name__ == '__main__':
    main()