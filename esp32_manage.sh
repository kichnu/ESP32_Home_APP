#!/bin/bash

# ESP32 Management Script - wersja z poprawionym resetem
# Automatyczne zarządzanie projektem MicroPython na ESP32

DEVICE="/dev/ttyACM0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kolory dla lepszej czytelności
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funkcja wyświetlająca nagłówek
print_header() {
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}================================${NC}"
}

# Funkcja wyświetlająca błąd
print_error() {
    echo -e "${RED}Błąd: $1${NC}"
}

# Funkcja wyświetlająca sukces
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Funkcja do bezpiecznego resetu
safe_reset() {
    # Metoda 1: Przez exec z timeout
    if command -v timeout &> /dev/null; then
        timeout 2 mpremote connect $DEVICE exec "import machine; machine.reset()" 2>/dev/null || true
    else
        # Metoda 2: Bez timeout, ale z przekierowaniem błędów
        mpremote connect $DEVICE exec "import machine; machine.reset()" 2>/dev/null &
        RESET_PID=$!
        sleep 2
        kill $RESET_PID 2>/dev/null || true
    fi
    sleep 1
}

# Funkcja do wgrywania projektu na ESP32
upload_project() {
    print_header "Wgrywanie projektu na ESP32"
    
    # Usuwanie starego folderu src
    echo "Usuwanie starego folderu src..."
    mpremote connect $DEVICE fs rm -r :src 2>/dev/null || true
    
    # Tworzenie folderu src
    echo "Tworzenie folderu src..."
    mpremote connect $DEVICE fs mkdir :src 2>/dev/null || true
    
    # Kopiowanie plików z src/
    if [ -d "src" ] && [ "$(ls -A src/*.py 2>/dev/null)" ]; then
        echo "Kopiowanie plików z src/..."
        for file in src/*.py; do
            if [ -f "$file" ]; then
                filename=$(basename "$file")
                echo "  Kopiowanie: $filename"
                mpremote connect $DEVICE fs cp "$file" ":src/$filename"
            fi
        done
        print_success "Pliki z src/ skopiowane"
    else
        print_error "Brak plików *.py w folderze src/"
    fi
    
    # Kopiowanie main.py
    if [ -f "main.py" ]; then
        echo "Kopiowanie main.py..."
        mpremote connect $DEVICE fs cp main.py :main.py
        print_success "main.py skopiowany"
    else
        print_error "Brak pliku main.py"
    fi
    
    # Reset ESP32
    echo "Resetowanie ESP32..."
    safe_reset
    print_success "ESP32 zresetowane"
    
    print_success "Projekt wgrany pomyślnie!"
}

# Funkcja czyszcząca folder src na ESP32
clean_src() {
    print_header "Czyszczenie folderu src na ESP32"
    mpremote connect $DEVICE fs rm -r :src 2>/dev/null || true
    print_success "Folder src wyczyszczony"
}

# Funkcja czyszcząca całą pamięć ESP32
clean_all() {
    print_header "Czyszczenie całej pamięci ESP32"
    echo "UWAGA: Ta operacja usunie WSZYSTKIE pliki z ESP32!"
    echo -n "Czy na pewno chcesz kontynuować? (t/n): "
    read -r confirmation
    
    if [ "$confirmation" != "t" ] && [ "$confirmation" != "T" ]; then
        print_error "Operacja anulowana"
        return
    fi
    
    echo "Pobieranie listy plików..."
    # Pobierz listę wszystkich plików i folderów
    files=$(mpremote connect $DEVICE fs ls : | grep -v "^d" | awk '{print $NF}')
    dirs=$(mpremote connect $DEVICE fs ls : | grep "^d" | awk '{print $NF}' | grep -v "^\." | grep -v "^/")
    
    # Usuń wszystkie pliki
    for file in $files; do
        if [ -n "$file" ]; then
            echo "Usuwanie pliku: $file"
            mpremote connect $DEVICE fs rm ":$file" 2>/dev/null || true
        fi
    done
    
    # Usuń wszystkie foldery
    for dir in $dirs; do
        if [ -n "$dir" ]; then
            echo "Usuwanie folderu: $dir"
            mpremote connect $DEVICE fs rm -r ":$dir" 2>/dev/null || true
        fi
    done
    
    print_success "Pamięć ESP32 wyczyszczona"
    echo "Uwaga: System plikowy MicroPython pozostaje nienaruszony"
}

# Funkcja formatująca system plików ESP32
format_filesystem() {
    print_header "Formatowanie systemu plików ESP32"
    echo "UWAGA: Ta operacja SFORMATUJE system plików!"
    echo "Wszystkie dane zostaną bezpowrotnie usunięte!"
    echo -n "Czy na pewno chcesz kontynuować? (t/n): "
    read -r confirmation
    
    if [ "$confirmation" != "t" ] && [ "$confirmation" != "T" ]; then
        print_error "Operacja anulowana"
        return
    fi
    
    echo "Formatowanie systemu plików..."
    # Formatowanie przez wykonanie kodu Python na ESP32
    mpremote connect $DEVICE exec "
import os
try:
    import machine
    # Formatuj system plików
    os.umount('/')
    os.VfsFat.mkfs(machine.Flash())
    os.mount(machine.Flash(), '/')
    print('System plików sformatowany pomyślnie')
except Exception as e:
    print('Błąd formatowania:', e)
    # Alternatywna metoda dla niektórych płytek
    try:
        import flashbdev
        os.umount('/')
        flashbdev.bdev.ioctl(5, 0)  # Erase all
        os.VfsFat.mkfs(flashbdev.bdev)
        os.mount(flashbdev.bdev, '/')
        print('System plików sformatowany pomyślnie (metoda alternatywna)')
    except Exception as e2:
        print('Błąd formatowania (metoda alternatywna):', e2)
"
    
    # Reset po formatowaniu
    echo "Resetowanie ESP32..."
    safe_reset
    
    print_success "System plików sformatowany i ESP32 zresetowane"
}

# Funkcja resetująca ESP32
reset_esp32() {
    print_header "Resetowanie ESP32"
    safe_reset
    print_success "ESP32 zresetowane"
}

# Funkcja listująca pliki na ESP32
list_files() {
    print_header "Pliki na ESP32"
    echo "Zawartość głównego katalogu:"
    mpremote connect $DEVICE fs ls -la :
    echo -e "\nZawartość folderu src:"
    mpremote connect $DEVICE fs ls -la :src 2>/dev/null || echo "Folder src nie istnieje"
}

# Funkcja kopiująca main.py z ESP32
copy_from_esp32() {
    print_header "Kopiowanie main.py z ESP32"
    if mpremote connect $DEVICE fs cp :main.py main_from_esp32.py; then
        print_success "main.py skopiowany jako main_from_esp32.py"
    else
        print_error "Nie udało się skopiować main.py"
    fi
}

# Funkcja uruchamiająca monitor portu szeregowego
serial_monitor() {
    print_header "Monitor portu szeregowego"
    echo "Łączenie z $DEVICE (115200 baud)"
    echo "Aby wyjść: Ctrl+A, potem K, potem Y"
    echo ""
    screen $DEVICE 115200
}

# Funkcja pokazująca pomoc
show_help() {
    print_header "ESP32 Management Script - Pomoc"
    echo "Użycie: $0 [opcja]"
    echo ""
    echo "Opcje:"
    echo "  upload     - Wgraj cały projekt na ESP32"
    echo "  clean      - Wyczyść folder src na ESP32"
    echo "  clean-all  - Wyczyść całą pamięć ESP32 (usuń wszystkie pliki)"
    echo "  format     - Sformatuj system plików ESP32"
    echo "  reset      - Zresetuj ESP32"
    echo "  list       - Wylistuj pliki na ESP32"
    echo "  copy       - Skopiuj main.py z ESP32"
    echo "  monitor    - Uruchom monitor portu szeregowego"
    echo "  help       - Pokaż tę pomoc"
    echo ""
    echo "Bez argumentów: Wgraj projekt (domyślnie)"
}

# Główna logika skryptu
case "${1:-upload}" in
    upload)
        upload_project
        ;;
    clean)
        clean_src
        ;;
    clean-all)
        clean_all
        ;;
    format)
        format_filesystem
        ;;
    reset)
        reset_esp32
        ;;
    list)
        list_files
        ;;
    copy)
        copy_from_esp32
        ;;
    monitor)
        serial_monitor
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Nieznana opcja: $1"
        show_help
        exit 1
        ;;
esac