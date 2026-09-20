from django.db import migrations, models
import django.db.models.deletion
import recetasApp.models


class Migration(migrations.Migration):

    dependencies = [
        ('recetasApp', '0007_chef_y_nombre_votante'),
    ]

    operations = [
        migrations.CreateModel(
            name='Comentario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, validators=[recetasApp.models.validar_nombre_completo])),
                ('texto', models.TextField(max_length=500)),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('receta', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comentarios', to='recetasApp.receta')),
            ],
            options={
                'ordering': ['-fecha'],
            },
        ),
    ]
