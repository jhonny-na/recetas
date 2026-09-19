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

class Receta(models.Model):
    nombre = models.CharField(max_length=200)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='otros')
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
    nombre = models.CharField(max_length=100)
    puntaje = models.PositiveIntegerField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('receta', 'nombre')

    def __str__(self):
        return f"{self.nombre}: {self.puntaje}★ en {self.receta.nombre}"