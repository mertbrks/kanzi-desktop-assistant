# Windows'un kendi OCR'ı (Türkçe) ile bir resimdeki yazıları satır satır çıkarır: "x,y<TAB>metin" (satırın sol üstü, resim pikseli)
param([string]$Resim)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq "AsTask" -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation``1" } |
    Select-Object -First 1
function Bekle($islem, [Type]$tur) { $t = $asTask.MakeGenericMethod($tur).Invoke($null, @($islem)); $t.Wait(); $t.Result }

$dosya = Bekle ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Resim)) ([Windows.Storage.StorageFile])
$akis = Bekle ($dosya.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$coz = Bekle ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($akis)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Bekle ($coz.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("tr"))
if (-not $motor) { $motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
$sonuc = Bekle ($motor.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
foreach ($satir in $sonuc.Lines) {
    $k = (@($satir.Words) | Select-Object -First 1).BoundingRect
    "{0},{1}`t{2}" -f [int]$k.X, [int]$k.Y, $satir.Text
}
$akis.Dispose()
