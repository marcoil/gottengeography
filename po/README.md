# Translating GottenGeography

1. Create the portable object template file, `gottengeography.pot`:
    
        $ cd po/
        $ ./initialize-pot.sh
    
    This script will tell you what languages exist and how complete those
    translations are. It will also ensure that the source code line number
    references in the template are up-to-date. If you're ever unsure of the
    context of a given string for translation, you can look up that line number
    in the source code and determine how that string is used to make sure it
    makes sense in context.
    
2. Create a new `[locale].po` file with `msginit`:
    
        $ msginit --input=gottengeography.pot --locale=[locale]
    
    (where `[locale]` is a locale code like `en_GB` or `zh_CN`)
    
3. Edit `[locale].po` with the translations correct for your language.
    
4. Compile and install it with distutils:
    
        $ cd ..
        $ sudo ./setup.py install
    
5. Run it!
    
        $ LANG=[locale].UTF-8 ./gottengeography
    
    And you should see your translation appear!
    
6. Send the `[locale].po` file to me (rbpark@exolucere.ca) and I'll include it
with future releases of GottenGeography for all to enjoy.
