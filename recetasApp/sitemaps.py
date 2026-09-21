from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Receta


class RecetaSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Receta.objects.all()

    def location(self, obj):
        return reverse('detalle_receta', args=[obj.id])


class PaginasEstaticasSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return ['inicio', 'lista_recetas']

    def location(self, item):
        return reverse(item)
