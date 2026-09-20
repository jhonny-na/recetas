from django.core.exceptions import ValidationError
from django.db import models

CATEGORIA_CHOICES = [
    ('pasteleria', 'Pastelería'),
    ('panaderia', 'Panadería'),
    ('almuerzos', 'Almuerzos'),
    ('postres', 'Postres'),
    ('otros', 'Otros'),
]

DIFICULTAD_CHOICES = [
    ('facil', 'Fácil'),
    ('media', 'Media'),
    ('dificil', 'Difícil'),
]

CHEF_CHOICES = [
    ('Catalina', 'Catalina'),
    ('Yesby', 'Yesby'),
]


def normalizar_nombre(nombre):
    """
    Limpia espacios de sobra y deja cada palabra con la primera letra en mayúscula.
    'juan   PÉREZ' -> 'Juan Pérez'
    Así 'juan pérez' y 'JUAN PÉREZ' se guardan igual y cuentan como la misma persona.
    """
    return " ".join((nombre or "").split()).title()


def validar_nombre_completo(nombre):
    """Obliga a escribir al menos nombre y apellido."""
    if len((nombre or "").split()) < 2:
        raise ValidationError("Escribe tu nombre y apellido (por ejemplo: Juan Pérez).")


class Receta(models.Model):
    nombre = models.CharField(max_length=200)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='otros')
    chef = models.CharField(max_length=50, choices=CHEF_CHOICES, blank=True)
    ingredientes = models.TextField()
    preparacion = models.TextField()
    imagen = models.ImageField(upload_to='recetas/', blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    tiempo_preparacion = models.CharField(max_length=50, blank=True, help_text="Ej: 30 min")
    porciones = models.PositiveIntegerField(blank=True, null=True)
    dificultad = models.CharField(max_length=10, choices=DIFICULTAD_CHOICES, blank=True)
    favorito = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre

    @property
    def promedio_valoracion(self):
        valoraciones = self.valoraciones.all()
        if not valoraciones:
            return 0
        return round(sum(v.puntaje for v in valoraciones) / valoraciones.count(), 1)

    @property
    def total_valoraciones(self):
        return self.valoraciones.count()


class Valoracion(models.Model):
    receta = models.ForeignKey(Receta, related_name='valoraciones', on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100, validators=[validar_nombre_completo])
    puntaje = models.PositiveIntegerField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('receta', 'nombre')

    def save(self, *args, **kwargs):
        # Siempre se guarda normalizado, así no se duplican por mayúsculas/minúsculas
        self.nombre = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre}: {self.puntaje}★ en {self.receta.nombre}"
