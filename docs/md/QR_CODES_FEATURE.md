# QR-коды для FilamentHub - Детальная концепция

> **Статус:** Planned (Фаза 8)  
> **Приоритет:** ⭐ Killer Feature  
> **Дата:** 2025-10-31

---

## 🎯 Проблема

Сейчас:
1. Пользователь купил катушку
2. Открывает сайт/OrcaSlicer
3. Ищет материал по названию
4. Скачивает профиль
5. Применяет настройки

**Слишком много шагов! 😩**

---

## 💡 Решение

**QR-код на коробке/катушке:**
1. Купил катушку → увидел QR
2. Отсканировал телефоном
3. Профиль автоматически импортирован ✨

---

## 🏗️ Архитектура

### Backend API

```python
# 1. Генерация QR-кода (для производителя)
POST /api/v1/filaments/{id}/qr-code
Headers:
  Authorization: Bearer {brand_jwt_token}

Response:
{
  "short_code": "FHUB-A3B9-X7K2",
  "qr_url": "https://filamenthub.ru/f/A3B9X7K2",
  "qr_image_png": "https://cdn.filamenthub.ru/qr/A3B9X7K2.png",
  "qr_image_svg": "https://cdn.filamenthub.ru/qr/A3B9X7K2.svg",
  "qr_data_uri": "data:image/png;base64,iVBORw0KG...",
  "deep_link": "filamenthub://import/A3B9X7K2",
  "expires_at": null,  // не истекает
  "created_at": "2025-10-31T12:00:00Z"
}

# 2. Редирект по короткому коду (для пользователя)
GET /f/{short_code}
→ 302 Redirect → /filaments/{id}?source=qr

# 3. Импорт по коду (для OrcaSlicer)
GET /api/v1/import/{short_code}
Response:
{
  "filament": {
    "id": 123,
    "name": "Bestfilament PLA Red",
    "brand": {"name": "Bestfilament", "verified": true},
    "material_type": "PLA",
    "color_hex": "#FF0000"
  },
  "profile": {
    // OrcaSlicer JSON format
    "filament_type": "PLA",
    "temperature": [210, 220],
    "bed_temperature": [60, 70],
    // ... полный профиль
  },
  "download_url": "https://filamenthub.ru/api/v1/filaments/123/profile.json"
}

# 4. Статистика сканирований (для производителя)
GET /api/v1/filaments/{id}/qr-stats
Response:
{
  "total_scans": 1523,
  "scans_last_30_days": 234,
  "scans_by_date": [
    {"date": "2025-10-01", "count": 12},
    {"date": "2025-10-02", "count": 15},
    // ...
  ],
  "top_countries": [
    {"country": "RU", "count": 1200},
    {"country": "BY", "count": 200},
    {"country": "KZ", "count": 123}
  ]
}
```

### Database Models

```python
class QRCode(Base):
    """QR-код для материала."""
    
    __tablename__ = "qr_codes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    filament_id: Mapped[int] = mapped_column(ForeignKey("filaments.id"))
    
    # Короткий код
    short_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    # Пример: FHUB-A3B9-X7K2
    
    # URLs
    qr_url: Mapped[str]  # https://filamenthub.ru/f/A3B9X7K2
    deep_link: Mapped[str]  # filamenthub://import/A3B9X7K2
    
    # Images (храним пути к файлам)
    qr_image_png: Mapped[str]  # /static/qr/A3B9X7K2.png
    qr_image_svg: Mapped[str]  # /static/qr/A3B9X7K2.svg
    
    # Статистика
    total_scans: Mapped[int] = mapped_column(default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    # Relationships
    filament: Mapped["Filament"] = relationship(back_populates="qr_codes")
    scans: Mapped[list["QRScan"]] = relationship(back_populates="qr_code")


class QRScan(Base):
    """История сканирований QR-кодов."""
    
    __tablename__ = "qr_scans"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    qr_code_id: Mapped[int] = mapped_column(ForeignKey("qr_codes.id"))
    
    # Метаданные
    scanned_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
    ip_address: Mapped[str] = mapped_column(String(45))  # IPv6 ready
    user_agent: Mapped[str | None] = mapped_column(String(512))
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1
    
    # Результат
    action: Mapped[str]  # "view", "download", "import"
    
    # Relationships
    qr_code: Mapped["QRCode"] = relationship(back_populates="scans")
```

### QR Generator Service

```python
# backend/app/services/qr_generator.py

import qrcode
import qrcode.image.svg
from io import BytesIO
import base64
import secrets

class QRGeneratorService:
    """Генерация QR-кодов для материалов."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = "https://filamenthub.ru"
    
    def generate_short_code(self) -> str:
        """Генерирует уникальный короткий код."""
        # Формат: FHUB-XXXX-XXXX (читаемый)
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без O, 0, I, 1
        part1 = ''.join(secrets.choice(alphabet) for _ in range(4))
        part2 = ''.join(secrets.choice(alphabet) for _ in range(4))
        return f"FHUB-{part1}-{part2}"
    
    async def create_qr_code(self, filament_id: int) -> QRCode:
        """Создать QR-код для материала."""
        
        # Проверяем существующий
        existing = await self.db.execute(
            select(QRCode).where(QRCode.filament_id == filament_id)
        )
        if qr := existing.scalar_one_or_none():
            return qr  # уже есть
        
        # Генерируем уникальный код
        while True:
            short_code = self.generate_short_code()
            exists = await self.db.execute(
                select(QRCode).where(QRCode.short_code == short_code)
            )
            if not exists.scalar_one_or_none():
                break
        
        # URLs
        qr_url = f"{self.base_url}/f/{short_code}"
        deep_link = f"filamenthub://import/{short_code}"
        
        # Генерируем изображения
        png_path = self._generate_png(qr_url, short_code)
        svg_path = self._generate_svg(qr_url, short_code)
        
        # Создаём запись
        qr_code = QRCode(
            filament_id=filament_id,
            short_code=short_code,
            qr_url=qr_url,
            deep_link=deep_link,
            qr_image_png=png_path,
            qr_image_svg=svg_path,
        )
        
        self.db.add(qr_code)
        await self.db.commit()
        await self.db.refresh(qr_code)
        
        return qr_code
    
    def _generate_png(self, url: str, code: str) -> str:
        """Генерирует PNG изображение QR."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Сохраняем в /static/qr/
        path = f"static/qr/{code}.png"
        img.save(path)
        
        return f"/static/qr/{code}.png"
    
    def _generate_svg(self, url: str, code: str) -> str:
        """Генерирует SVG изображение QR."""
        factory = qrcode.image.svg.SvgPathImage
        qr = qrcode.QRCode(image_factory=factory)
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image()
        
        # Сохраняем в /static/qr/
        path = f"static/qr/{code}.svg"
        with open(path, 'wb') as f:
            img.save(f)
        
        return f"/static/qr/{code}.svg"
    
    async def track_scan(
        self,
        short_code: str,
        ip_address: str,
        user_agent: str | None,
        action: str = "view",
    ):
        """Отследить сканирование QR-кода."""
        qr_code = await self.get_by_short_code(short_code)
        if not qr_code:
            return
        
        # Определяем страну по IP (используем geoip2 или ipapi.co)
        country = await self._get_country_from_ip(ip_address)
        
        # Создаём запись
        scan = QRScan(
            qr_code_id=qr_code.id,
            scanned_at=datetime.utcnow(),
            ip_address=ip_address,
            user_agent=user_agent,
            country=country,
            action=action,
        )
        
        self.db.add(scan)
        
        # Обновляем счётчик
        qr_code.total_scans += 1
        
        await self.db.commit()
```

---

## 🎨 Frontend (Web UI)

### Brand Dashboard

```tsx
// Страница материала в dashboard производителя
const FilamentQRCode: React.FC<{filament: Filament}> = ({filament}) => {
  const {data: qrCode, isLoading} = useQuery({
    queryKey: ['qr-code', filament.id],
    queryFn: () => api.post(`/filaments/${filament.id}/qr-code`),
  });
  
  if (isLoading) return <Spinner />;
  
  return (
    <Card>
      <CardHeader>
        <CardTitle>QR-код для быстрого импорта</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-4">
          {/* QR изображение */}
          <div className="flex flex-col items-center gap-2">
            <img 
              src={qrCode.qr_image_png} 
              alt="QR Code"
              className="w-48 h-48"
            />
            <p className="text-sm font-mono">{qrCode.short_code}</p>
          </div>
          
          {/* Действия */}
          <div className="flex flex-col gap-2">
            <Button onClick={() => download(qrCode.qr_image_png)}>
              Скачать PNG
            </Button>
            <Button onClick={() => download(qrCode.qr_image_svg)}>
              Скачать SVG (для печати)
            </Button>
            <Button variant="outline" onClick={() => copy(qrCode.qr_url)}>
              Копировать ссылку
            </Button>
          </div>
        </div>
        
        {/* Статистика */}
        <div className="mt-4">
          <h4>Статистика сканирований</h4>
          <p>Всего: {qrCode.total_scans}</p>
          <p>За последние 30 дней: {stats.scans_last_30_days}</p>
        </div>
      </CardContent>
    </Card>
  );
};
```

### Landing Page (после скана)

```tsx
// /f/{short_code} страница
const QRLandingPage: React.FC = () => {
  const {short_code} = useParams();
  const {data: filament} = useQuery({
    queryKey: ['import', short_code],
    queryFn: () => api.get(`/import/${short_code}`),
  });
  
  return (
    <div className="max-w-md mx-auto p-4">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <div 
              className="w-12 h-12 rounded-full"
              style={{backgroundColor: filament.color_hex}}
            />
            <div>
              <h2>{filament.name}</h2>
              <p className="text-sm text-muted-foreground">
                {filament.brand.name} {filament.brand.verified && '✓'}
              </p>
            </div>
          </div>
        </CardHeader>
        
        <CardContent>
          {/* Главная кнопка */}
          <Button 
            size="lg" 
            className="w-full"
            onClick={handleImport}
          >
            🚀 Импортировать в OrcaSlicer
          </Button>
          
          {/* Альтернатива */}
          <div className="mt-4 text-center">
            <p className="text-sm text-muted-foreground">
              Или введите код в OrcaSlicer:
            </p>
            <code className="text-lg font-mono">{short_code}</code>
          </div>
          
          {/* Информация */}
          <div className="mt-4">
            <h4>Настройки:</h4>
            <ul>
              <li>Температура: {filament.settings.extruder_temp}°C</li>
              <li>Стол: {filament.settings.bed_temp}°C</li>
              <li>Скорость: {filament.settings.print_speed} mm/s</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
```

---

## 🖥️ OrcaSlicer Integration

```cpp
// src/slic3r/GUI/FilamentHubPanel.cpp

void FilamentHubPanel::create_import_section()
{
    // Секция "Импорт по коду"
    auto* import_box = new wxStaticBoxSizer(wxVERTICAL, this, "Импорт по QR-коду");
    
    auto* code_sizer = new wxBoxSizer(wxHORIZONTAL);
    
    m_import_code_input = new wxTextCtrl(this, wxID_ANY, "FHUB-",
                                         wxDefaultPosition, wxSize(150, -1));
    m_import_code_input->SetHint("FHUB-XXXX-XXXX");
    
    auto* import_btn = new wxButton(this, wxID_ANY, "Импортировать");
    
    code_sizer->Add(m_import_code_input, 1, wxRIGHT, 5);
    code_sizer->Add(import_btn, 0);
    
    import_box->Add(code_sizer, 0, wxEXPAND | wxALL, 5);
    
    // Bind event
    import_btn->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_import_by_code, this);
}

void FilamentHubPanel::on_import_by_code(wxCommandEvent& event)
{
    std::string code = m_import_code_input->GetValue().ToStdString();
    
    // Validate format
    if (!validate_short_code(code)) {
        show_error("Неверный формат кода. Используйте FHUB-XXXX-XXXX");
        return;
    }
    
    // API request
    std::string url = m_base_url + "/api/v1/import/" + code;
    
    auto http = Http::get(url);
    http.on_complete([this](std::string body, unsigned status) {
        if (status == 200) {
            auto j = json::parse(body);
            
            // Download and save profile
            std::string profile_json = j["profile"].dump();
            save_profile_from_json(profile_json, j["filament"]["name"]);
            
            show_message("Профиль успешно импортирован!");
        } else {
            show_error("Не удалось найти материал по коду");
        }
    });
    http.perform_sync();
}
```

---

## 📋 Материалы для производителей

### Шаблон для печати (A4 лист)

```
┌────────────────────────────────────────┐
│  FILAMENTHUB QR-КОД                    │
│                                        │
│  ┌────────────────────┐                │
│  │                    │                │
│  │   [QR CODE 5x5cm]  │                │
│  │                    │                │
│  └────────────────────┘                │
│                                        │
│  Bestfilament PLA Red                  │
│  Код: FHUB-A3B9-X7K2                   │
│                                        │
│  Отсканируйте для автоматической       │
│  загрузки настроек в OrcaSlicer        │
│                                        │
│  filamenthub.ru                        │
└────────────────────────────────────────┘

Линия отреза (вырезать и наклеить на коробку)
```

---

## 🎯 Метрики успеха

- 50%+ производителей генерируют QR-коды
- 30%+ пользователей импортируют через QR (vs ручной поиск)
- Средняя конверсия: скан QR → импорт профиля = 80%

---

## 🚀 Roadmap

1. **Фаза 8.1** - Backend API (генерация QR, статистика)
2. **Фаза 8.1** - Web UI (dashboard для брендов, landing page)
3. **Фаза 8.1** - OrcaSlicer integration (импорт по коду)
4. **Фаза 8.1** - Deep link поддержка (опционально)
5. **Фаза 8.1** - Маркетинг (шаблоны, инструкции)

---

**Эта фича сделает FilamentHub незаменимым для производителей!** 🚀

