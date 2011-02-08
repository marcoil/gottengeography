Translating GottenGeography:

1. Create a new po file with msginit:
    
        $ cd po/
        $ msginit --input=gottengeography.pot --locale=[language]
    
    (where [language] is something like en_GB or zh_CN)
    
2. Edit [language].po with the translations correct for your language.
    
3. Compile and install it with distutils:
    
        $ cd ..
        $ sudo ./setup.py install
    
4. Run it!
    
        $ LANG=[language].utf8 ./gottengeography
    
    And you should see your translation appear!
    
5. Send the [language].po file to me (rbpark@exolucere.ca) and I'll include it
with future releases of GottenGeography for all to enjoy.
