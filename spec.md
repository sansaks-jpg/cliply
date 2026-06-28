fix seluruh masalah ini, selalu mengacu pada context7 dan kalo bisa resolve masalahnya dengan melihat repository opensource orang, jangan membuat manual (tiru dan modifikasi).

1. fix bug kamera tracker yg selalu pusing/jitter trackingnya gk mulus.
2. sensitivitas deteksi costum di frontend hapus, sebagai gantinya kamu lakukan debugging terhadap model yunet mediapipe dan yolo, di threshold mana dia akurat dan bagus untuk deteksi wajah.
3. tracking ai nya masih gk mulus, antara yg ngomong siapa dan yg tidak, misalnya ada 2 orang yg ngomong, dia malah suka ngetrack nya yg gk ngomong.
4. fix caption yg ada tanda koma petik dll (hapus tanda ini, ajdi bersih hanya text)
5. di frontend, tambahkan ui baru untuk melihat task yg lagi aktif, menyala atau gimana gitu, taruh paling atas, jadi user bisa langsung klik task yg lagi running.
6. Ketika user paste url yt di inputnya, bakal diproses fetch dlu dibelakang - nanti muncul judul kontennya, barus user bisa klik buat clip (Ketika proses, tombolnya berubah jadi loading dan gk bisa diklik).
7. cek pr di gh, untuk melakukan merge harus sesuai aturan CLAUDE.md, lakukan merge dan close pr yg ada.
8. verifikasi semuanya dengan cek syntax
9. push ke gh dengan commit Bahasa inggris lalu trigger action build tauri (dengan versi 0.1.7)
10. buat monitor terhadap build tersebut setiap 5 menit sekali, jika sudah selesai maka download filenya dan simpan di folder download.
11. hapus file ini jika semuanya selesai.

